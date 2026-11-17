"""Finds Claude Code and Codex session files and splits each one into per-day slices.

Standard library only, Python 3.9+ (the python3 that ships with macOS).

A session can run past midnight. Every line is put under the local date of its own timestamp, so a session used
on the 17th and the 18th becomes two slices: the 17th's lines and the 18th's lines. Lines without a timestamp go
with the line before them.
"""
import datetime
import glob
import hashlib
import json
import os
import re

# Internal dumps, not conversation. In the largest sessions on one machine they were more than half the bytes.
DROP_TYPES = {"api-request", "api-request-blob", "api-request-shape", "file-history-snapshot"}
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
SAFE_ID = re.compile(r"[^A-Za-z0-9._-]")
ISO = re.compile(r"(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d)(?:\.(\d+))?\s*(Z|[+-]\d\d:?\d\d)?$")


def _env(name):
    return os.environ.get("SESSION_RELAY_" + name)


def claude_projects_dir():
    if _env("CLAUDE_DIR"):
        return os.path.expanduser(_env("CLAUDE_DIR"))
    base = os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude"
    return os.path.join(os.path.expanduser(base), "projects")


def codex_home():
    return os.path.expanduser(_env("CODEX_DIR") or os.environ.get("CODEX_HOME") or "~/.codex")


def _imported_codex_ids(home):
    """Codex can import Claude Code sessions. Those copies would send the same conversation twice."""
    try:
        with open(os.path.join(home, "external_agent_session_imports.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return set()
    records = data.get("records") if isinstance(data, dict) else None
    return {r.get("imported_thread_id") for r in records or [] if isinstance(r, dict) and r.get("imported_thread_id")}


def safe_id(text):
    return SAFE_ID.sub("_", text)[:100] or "unknown"


def find_session_files():
    """Every session file on this computer: [{tool, session_id, path}]. Subagent records are not included."""
    found = {}

    def add(tool, sid, path):
        key = (tool, sid)
        old = found.get(key)
        # The same Codex session can sit in sessions/ and archived_sessions/. Keep the newer copy.
        if old is None or os.path.getmtime(path) > os.path.getmtime(old["path"]):
            found[key] = {"tool": tool, "session_id": sid, "path": path}

    # Claude Code: projects/<project>/<session id>.jsonl. Subagents live one level deeper and are left out.
    for path in glob.glob(os.path.join(claude_projects_dir(), "*", "*.jsonl")):
        add("claude", safe_id(os.path.basename(path)[:-len(".jsonl")]), path)

    home = codex_home()
    imported = _imported_codex_ids(home)
    paths = glob.glob(os.path.join(home, "sessions", "*", "*", "*", "rollout-*.jsonl"))
    paths += glob.glob(os.path.join(home, "archived_sessions", "rollout-*.jsonl"))
    for path in paths:
        ids = UUID.findall(os.path.basename(path))
        sid = ids[-1].lower() if ids else os.path.basename(path)[:-len(".jsonl")]
        if sid in imported:
            continue
        add("codex", safe_id(sid), path)
    return sorted(found.values(), key=lambda f: f["path"])


def local_day(value):
    """The local date (YYYY-MM-DD) of an ISO timestamp or epoch number, or None."""
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            seconds = value / 1000.0 if value > 1e11 else float(value)
            return datetime.datetime.fromtimestamp(seconds).date().isoformat()
        if not isinstance(value, str):
            return None
        m = ISO.match(value.strip())
        if not m:
            return None
        y, mo, d, h, mi, s, frac, zone = m.groups()
        micro = int((frac or "0")[:6].ljust(6, "0"))
        moment = datetime.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s), micro)
        if zone is None:
            return moment.date().isoformat()  # Already local.
        if zone == "Z":
            offset = datetime.timedelta(0)
        else:
            sign = -1 if zone[0] == "-" else 1
            digits = zone[1:].replace(":", "")
            offset = sign * datetime.timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
        aware = moment.replace(tzinfo=datetime.timezone(offset))
        return aware.astimezone().date().isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def _automated(tool, obj):
    """Runs started by a program, not a person: `claude -p` and `codex exec`."""
    if tool == "claude":
        return obj.get("entrypoint") == "sdk-cli"
    if obj.get("type") == "session_meta":
        payload = obj.get("payload") or {}
        source = payload.get("source")
        return source == "exec" or payload.get("originator") == "codex_exec" or isinstance(source, dict)
    return False


def read_slices(entry):
    """Reads one session file and splits it by day.

    Returns {"automated": bool, "cwd": str|None, "days": {date: {"data": bytes, "lines": n, "first": ts, "last": ts}}}.
    An unfinished last line (the tool is still writing it) is left for the next run.
    """
    tool = entry["tool"]
    days = {}
    pending = []  # Lines before the first timestamp.
    current = None
    automated = False
    cwd = None

    def put(day, raw, stamp):
        slot = days.setdefault(day, {"parts": [], "lines": 0, "first": None, "last": None})
        slot["parts"].append(raw)
        slot["lines"] += 1
        if isinstance(stamp, str):
            slot["first"] = slot["first"] or stamp
            slot["last"] = stamp

    with open(entry["path"], "rb") as f:
        for raw in f:
            if not raw.strip():
                continue
            obj = None
            try:
                obj = json.loads(raw)
            except ValueError:
                if not raw.endswith(b"\n"):
                    break  # Unfinished tail.
            if not raw.endswith(b"\n"):
                raw += b"\n"
            stamp = None
            day = None
            if isinstance(obj, dict):
                if obj.get("type") in DROP_TYPES:
                    continue
                if not automated and _automated(tool, obj):
                    automated = True
                if cwd is None:
                    payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
                    cwd = obj.get("cwd") or payload.get("cwd")
                stamp = obj.get("timestamp")
                day = local_day(stamp)
            if day:
                if pending:
                    for p in pending:
                        put(day, p, None)
                    pending = []
                current = day
                put(day, raw, stamp)
            elif current:
                put(current, raw, None)
            else:
                pending.append(raw)
    if pending:
        day = datetime.date.fromtimestamp(os.path.getmtime(entry["path"])).isoformat()
        for p in pending:
            put(day, p, None)

    out = {}
    for day, slot in days.items():
        data = b"".join(slot["parts"])
        out[day] = {"data": data, "sha256": hashlib.sha256(data).hexdigest(), "lines": slot["lines"],
                    "first": slot["first"], "last": slot["last"]}
    return {"automated": automated, "cwd": cwd if isinstance(cwd, str) else None, "days": out}

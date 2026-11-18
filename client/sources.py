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

import media
import redact

# Internal dumps, not conversation. In the largest sessions on one machine they were more than half the bytes.
DROP_TYPES = {"api-request", "api-request-blob", "api-request-shape", "file-history-snapshot"}
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
SAFE_ID = re.compile(r"[^A-Za-z0-9._-]")
ISO = re.compile(r"(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d)(?:\.(\d+))?\s*(Z|[+-]\d\d:?\d\d)?$")


def _env(name):
    return os.environ.get("SESSION_RELAY_" + name)


def _unique(paths):
    seen, out = set(), []
    for p in paths:
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def claude_project_dirs():
    """Every place this computer could keep Claude Code sessions: the folder CLAUDE_CONFIG_DIR names, the default
    ~/.claude, and the XDG location some versions use. Only the ones that exist matter."""
    if _env("CLAUDE_DIR"):  # Tests and manual override: exactly this folder.
        return [os.path.expanduser(_env("CLAUDE_DIR"))]
    dirs = []
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        dirs.append(os.path.join(os.path.expanduser(os.environ["CLAUDE_CONFIG_DIR"]), "projects"))
    dirs.append(os.path.join(os.path.expanduser("~"), ".claude", "projects"))
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    dirs.append(os.path.join(os.path.expanduser(xdg), "claude", "projects"))
    return _unique(dirs)


def codex_homes():
    if _env("CODEX_DIR"):
        return [os.path.expanduser(_env("CODEX_DIR"))]
    homes = []
    if os.environ.get("CODEX_HOME"):
        homes.append(os.path.expanduser(os.environ["CODEX_HOME"]))
    homes.append(os.path.join(os.path.expanduser("~"), ".codex"))
    return _unique(homes)


def discover():
    """The folders on this computer that exist and could hold sessions: {"claude": [...], "codex": [...]}.
    The installer saves this, because the daily job does not get the terminal's environment variables."""
    return {"claude": [d for d in claude_project_dirs() if os.path.isdir(d)],
            "codex": [d for d in codex_homes() if os.path.isdir(d)]}


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


def find_session_files(saved=None):
    """Every session file on this computer: [{tool, session_id, path}]. Subagent records are not included.

    Looks in the places discover() names now plus the ones saved at install time (`saved`, from config.json).
    """
    found = {}
    saved = saved or {}

    def add(tool, sid, path):
        key = (tool, sid)
        old = found.get(key)
        # The same Codex session can sit in sessions/ and archived_sessions/. Keep the newer copy.
        if old is None or os.path.getmtime(path) > os.path.getmtime(old["path"]):
            found[key] = {"tool": tool, "session_id": sid, "path": path}

    # Claude Code: projects/<project>/<session id>.jsonl. Subagents live one level deeper and are left out.
    for folder in _unique(list(saved.get("claude") or []) + claude_project_dirs()):
        for path in glob.glob(os.path.join(folder, "*", "*.jsonl")):
            add("claude", safe_id(os.path.basename(path)[:-len(".jsonl")]), path)

    for home in _unique(list(saved.get("codex") or []) + codex_homes()):
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
    An unfinished last line (the tool is still writing it) is left for the next run. Images and other base64
    attachments are replaced with a short text note (see media.py), and secrets are masked (see redact.py).
    """
    tool = entry["tool"]
    days = {}
    pending = []  # Lines before the first timestamp.
    current = None
    automated = False
    cwd = None

    def put(day, raw, stamp, removed=0, masked=0):
        slot = days.setdefault(day, {"parts": [], "lines": 0, "first": None, "last": None, "media": 0, "secrets": 0})
        slot["parts"].append(raw)
        slot["lines"] += 1
        slot["media"] += removed
        slot["secrets"] += masked
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
            removed = 0
            if isinstance(obj, dict):
                if obj.get("type") in DROP_TYPES:
                    continue
                raw, removed = media.strip_line(raw, obj)
            # Every line, also ones that are not JSON objects. obj is stale once media.strip_line changed the line.
            raw, masked = redact.redact_line(raw, obj if obj is not None and not removed else None)
            if isinstance(obj, dict):
                if not automated and _automated(tool, obj):
                    automated = True
                if cwd is None:
                    payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
                    cwd = obj.get("cwd") or payload.get("cwd")
                stamp = obj.get("timestamp")
                day = local_day(stamp)
            if day:
                if pending:
                    for p, m in pending:
                        put(day, p, None, 0, m)
                    pending = []
                current = day
                put(day, raw, stamp, removed, masked)
            elif current:
                put(current, raw, None, removed, masked)
            else:
                pending.append((raw, masked))
    if pending:
        day = datetime.date.fromtimestamp(os.path.getmtime(entry["path"])).isoformat()
        for p, m in pending:
            put(day, p, None, 0, m)

    out = {}
    for day, slot in days.items():
        data = b"".join(slot["parts"])
        out[day] = {"data": data, "sha256": hashlib.sha256(data).hexdigest(), "lines": slot["lines"],
                    "first": slot["first"], "last": slot["last"], "media": slot["media"],
                    "secrets": slot["secrets"]}
    return {"automated": automated, "cwd": cwd if isinstance(cwd, str) else None, "days": out}

#!/usr/bin/env python3
"""session-relay: sends this computer's Claude Code and Codex conversations to the relay server, once a day.

Standard library only, Python 3.9+ (the python3 that ships with macOS). Installed by install.sh into
~/.session-relay/app; ~/.session-relay/relay runs it.

  init --code CODE   Check the code with the server, install, register the daily job and start the first upload.
  tick               What the daily job runs (at login and every hour). Syncs at most once a day.
  sync               Sync now, in the foreground, even if today was already synced.
  status [--json]    Show the state.
  stop               Stop for good on this computer: remove the job and stop calling the server.
  uninstall          stop, then remove ~/.session-relay and the optional skill.

Nothing is sent twice. Each session is split into one slice per local date (a session used across midnight gives
two slices) and the sha256 of every uploaded slice is kept. A slice is sent again only when it changed, which is
what happens to "today" when it is synced in the morning and the session goes on in the afternoon.

When the code's end time has passed, the job stops itself without calling the server. When the server says the
code has ended (or no longer exists), it stops the same way.

Messages are in Korean when the locale is Korean, otherwise in English.
"""
import argparse
import contextlib
import datetime
import gzip
import json
import os
import plistlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import redact  # noqa: E402
import sources  # noqa: E402

REPO_URL = "https://github.com/hack-vibe-x/hack-session-relay"
MESSAGES = {
    "not_setup": ("아직 설정되지 않았습니다. 접속 코드로 설치하세요: %s" % REPO_URL,
                  "Not set up yet. Install with your code: %s" % REPO_URL),
    "is_stopped": ("{date}에 멈췄습니다 ({reason}). 다시 시작하려면: ~/.session-relay/relay init --code <접속 코드>",
                   "Stopped on {date} ({reason}). To start again: ~/.session-relay/relay init --code <code>"),
    "busy": ("다른 동기화가 진행 중입니다.", "Another sync is running."),
    "server_retry": ("서버 오류입니다. 나중에 다시 시도합니다: {e}", "Server error, will retry later: {e}"),
    "net_retry": ("서버에 연결할 수 없습니다. 나중에 다시 시도합니다: {e}", "Could not reach the server, will retry later: {e}"),
    "synced": ("동기화 완료: 세션 {sessions}개, 조각 {slices}개, 압축 {mb:.1f} MB 전송.",
               "Synced: {slices} slices from {sessions} sessions, {mb:.1f} MB compressed."),
    "sync_errors": (" 오류 {n}건 (status에서 확인).", " {n} errors (see status)."),
    "no_server": ("서버 주소가 없습니다. --server https://... 로 알려 주세요.", "No server address. Pass --server https://..."),
    "code_invalid": ("접속 코드가 맞지 않습니다. 확인하고 다시 입력하세요.", "This code is not valid. Check it and try again."),
    "code_ended": ("이미 끝난 접속 코드입니다 ({end}). 관리자에게 새 코드를 받으세요.",
                   "This code has already ended ({end}). Ask the admin for a new one."),
    "refused": ("서버가 거절했습니다: {e}", "The server refused: {e}"),
    "unreachable": ("서버({server})에 연결할 수 없습니다. 아무것도 설치하지 않았습니다. 나중에 다시 실행하세요: {e}",
                    "Could not reach the server {server}. Nothing was installed; try again later: {e}"),
    "confirmed": ("접속 코드 확인: 사용자 {user}, {end}까지 사용.", "Code confirmed: user {user}, until {end}."),
    "never": ("기한 없음", "no end"),
    "notice": ("이 컴퓨터의 Claude Code·Codex 대화를 지금 서버로 보내고, 이후 하루 한 번 보냅니다. "
               "API 키·토큰·비밀번호와 이메일·전화번호는 이 컴퓨터에서 가린 뒤 보냅니다. 종료일이 지나면 저절로 멈춥니다.",
               "This computer's Claude Code and Codex conversations are sent now, then once a day, until the end date. "
               "API keys, tokens, passwords, email addresses and phone numbers are masked on this computer before sending."),
    "found": ("세션 파일 {n}개를 찾았습니다 (Claude Code {c}, Codex {x}).",
              "Found {n} session files (Claude Code {c}, Codex {x})."),
    "job_ok": ("매일 동기화 작업을 등록했습니다 (로그인할 때, 하루 한 번).", "Registered the daily job (at login, once a day)."),
    "job_fail": ("매일 동기화 작업을 등록하지 못했습니다: {e}", "Could not register the daily job: {e}"),
    "job_unsupported": ("매일 동기화는 지금은 macOS에서만 자동으로 등록됩니다. 하루 한 번 ~/.session-relay/relay tick 을 실행하세요.",
                        "The daily job is registered on macOS only for now. Run ~/.session-relay/relay tick once a day."),
    "no_job": ("매일 동기화 작업은 등록하지 않았습니다 (--no-job).", "No daily job (--no-job)."),
    "bg": ("첫 업로드를 백그라운드에서 시작했습니다. 확인: ~/.session-relay/relay status",
           "The first upload is running in the background. Check it: ~/.session-relay/relay status"),
    "fg": ("지금 업로드합니다.", "Uploading now."),
    "skill": ("Claude Code·Codex용 스킬도 설치했습니다. 대화창에서 \"세션 릴레이 상태 알려줘\"처럼 물어보면 됩니다.",
              "Installed the skill for Claude Code / Codex: ask \"session relay status\" in a chat."),
    "commands": ("명령: ~/.session-relay/relay status | sync | stop | uninstall",
                 "Commands: ~/.session-relay/relay status | sync | stop | uninstall"),
    "stopped": ("멈췄습니다 ({reason}). 이 컴퓨터는 더 이상 서버를 호출하지 않습니다. {detail}",
                "Stopped ({reason}). This computer no longer calls the server. {detail}"),
    "ended_at": ("접속 코드가 {end}에 끝났습니다.", "The code ended at {end}."),
    "uninstalled": ("삭제했습니다: {paths}", "Removed: {paths}"),
    "reason.expired": ("기간 종료", "ended"),
    "reason.invalid": ("코드 없음", "unknown code"),
    "reason.user": ("사용자가 멈춤", "stopped by user"),
    "st.user": ("사용자: {user}  서버: {server}", "User: {user}  Server: {server}"),
    "st.end": ("종료 시점: {end}", "Ends: {end}"),
    "st.stopped": ("멈춤: {at} ({reason})", "Stopped: {at} ({reason})"),
    "st.job": ("매일 동기화: {on}{running}", "Daily job: {on}{running}"),
    "st.on": ("켜짐", "on"), "st.off": ("꺼짐", "off"),
    "st.running": (", 지금 동기화 중", ", syncing now"),
    "st.last": ("마지막 동기화: {at}  ({detail})", "Last sync: {at}  ({detail})"),
    "st.sent": ("지금까지 보낸 것: 세션 {sessions}개, 조각 {slices}개", "Sent so far: {slices} slices from {sessions} sessions"),
    "st.error": ("오류: {e}", "error: {e}"),
}


def korean():
    lang = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
    if env("LANG"):
        lang = env("LANG")
    return lang.lower().startswith("ko")


def t(key, **kw):
    text = MESSAGES[key][0 if korean() else 1]
    return text.format(**kw) if kw else text


def reason_text(reason):
    key = {"expired": "reason.expired", "invalid": "reason.invalid", "stopped by user": "reason.user"}.get(reason)
    return t(key) if key else reason

VERSION = "0.5.0"
PREFIX = "[session-relay]"
LABEL = "io.session-relay.sync"
TIMEOUT = 180
MAX_SLICE_GZ = 95 * 1024 * 1024
SAVE_EVERY = 25
STALE_LOCK = 6 * 60 * 60


# ---------- Paths and files ----------

def env(name, default=None):
    return os.environ.get("SESSION_RELAY_" + name) or default


def home():
    return os.path.expanduser(env("HOME", "~/.session-relay"))


def path(*parts):
    return os.path.join(home(), *parts)


def label():
    return env("LABEL", LABEL)


def plist_path():
    return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents", label() + ".plist")


def say(msg):
    print("%s %s" % (PREFIX, msg), flush=True)


def log(msg):
    os.makedirs(path("logs"), exist_ok=True)
    with open(path("logs", "relay.log"), "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))


def read_json(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def load_config():
    return read_json(path("config.json"), {})


def save_config(cfg):
    write_json(path("config.json"), cfg)


def load_state():
    return read_json(path("state.json"), {})


def save_state(state):
    write_json(path("state.json"), state)


def defaults():
    return read_json(os.path.join(os.path.dirname(os.path.abspath(__file__)), "defaults.json"), {})


def now_utc():
    fake = env("NOW")  # Tests only.
    if fake:
        return datetime.datetime.fromisoformat(fake.replace("Z", "+00:00")).astimezone(datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc)


def today():
    return now_utc().astimezone().date().isoformat()


def parse_time(text):
    if not text:
        return None
    try:
        moment = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment


def normalize_code(code):
    return "".join(ch for ch in code.upper() if ch.isalnum())


# ---------- Server ----------

class ServerError(Exception):
    def __init__(self, status, body):
        Exception.__init__(self, "HTTP %s %s" % (status, body))
        self.status = status
        self.body = body if isinstance(body, dict) else {}


def ssl_context():
    ctx = ssl.create_default_context()
    try:
        import certifi  # Present on many machines; fixes python.org builds without system certificates.
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return ctx


def request(cfg, method, route, body=None, headers=None):
    url = cfg["server"].rstrip("/") + route
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", "Bearer " + cfg["code"])
    req.add_header("User-Agent", "session-relay/" + VERSION)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    ctx = ssl_context() if url.startswith("https") else None
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as res:
            raw = res.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            data = json.loads(raw)
        except ValueError:
            data = {"error": raw[:200].decode("utf-8", "replace")}
        raise ServerError(e.code, data)


def check_code(cfg):
    """GET /v1/me. Returns the server's view of the code, or raises ServerError."""
    return request(cfg, "GET", "/v1/me")


def ended_reason(err):
    """'expired' or 'invalid' when the server says this code can no longer be used, else None."""
    if err.status == 401:
        return "invalid"
    if err.status == 403 and err.body.get("status") in ("expired", "revoked"):
        return "expired"
    return None


# ---------- Daily job (launchd) ----------

def python_path():
    """A python3 path that survives updates. Shell-scoped shims (fnm, pyenv) are resolved."""
    found = shutil.which("python3") or sys.executable
    if "_multishells" in found or "/shims/" in found:
        return os.path.realpath(found)
    return os.path.abspath(found)


def copy_app():
    """The job runs from a copy in ~/.session-relay/app, so the download or clone can go away.
    Also writes ~/.session-relay/relay (the command) and ~/.session-relay/README.md (for people and AI agents)."""
    src = os.path.dirname(os.path.abspath(__file__))
    dest = path("app")
    if os.path.abspath(src) != os.path.abspath(dest):
        skill = skill_source()
        shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(dest)
        for name in ("relay.py", "sources.py", "media.py", "redact.py", "defaults.json"):
            if os.path.exists(os.path.join(src, name)):
                shutil.copy2(os.path.join(src, name), os.path.join(dest, name))
        if skill:
            os.makedirs(os.path.join(dest, "skill"))
            shutil.copy2(skill, os.path.join(dest, "skill", "SKILL.md"))
    script = os.path.join(dest, "relay.py")
    wrapper = path("relay")
    with open(wrapper, "w", encoding="utf-8") as f:
        f.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (python_path(), script))
    os.chmod(wrapper, 0o755)
    with open(path("README.md"), "w", encoding="utf-8") as f:
        f.write(LOCAL_README)
    return script


def skill_source():
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (os.path.join(os.path.dirname(here), "skill", "SKILL.md"), os.path.join(here, "skill", "SKILL.md")):
        if os.path.exists(candidate):
            return candidate
    return None


def skill_targets():
    """Claude Code reads ~/.claude/skills, Codex reads ~/.agents/skills. Only tools present on this computer."""
    user = os.path.expanduser("~")
    out = []
    if os.path.isdir(os.path.join(user, ".claude")):
        out.append(os.path.join(user, ".claude", "skills", "session-relay"))
    if os.path.isdir(os.path.join(user, ".codex")) or os.path.isdir(os.path.join(user, ".agents")):
        out.append(os.path.join(user, ".agents", "skills", "session-relay"))
    return out


def install_skill():
    source = skill_source()
    if not source:
        return []
    done = []
    for target in skill_targets():
        os.makedirs(target, exist_ok=True)
        shutil.copy2(source, os.path.join(target, "SKILL.md"))
        done.append(target)
    return done


LOCAL_README = """# session-relay

This computer sends its Claude Code and Codex conversation records to the session-relay server once a day,
until the code's end date. Source: %s

Commands (also for AI agents asked about "session relay"):

    ~/.session-relay/relay status            # user, end date, last sync, errors
    ~/.session-relay/relay sync              # sync now
    ~/.session-relay/relay stop              # stop for good on this computer
    ~/.session-relay/relay init --code SR-…  # change the code, or start again after stop
    ~/.session-relay/relay uninstall         # stop and remove everything here

Files: config.json (code, end date), state.json (what was sent), logs/relay.log.
""" % REPO_URL


def launchctl(*args):
    return subprocess.run(["launchctl"] + list(args), capture_output=True, text=True)


def domain():
    return "gui/%d" % os.getuid()


def job_loaded():
    if sys.platform != "darwin" or env("NO_LAUNCHD"):
        return False
    return launchctl("print", "%s/%s" % (domain(), label())).returncode == 0


def install_job():
    """Registers the job: at login (RunAtLoad) and on the hour. The tick itself makes it once a day.
    Loading it runs it right away, which starts the first upload in the background."""
    script = path("app", "relay.py")
    if sys.platform != "darwin" or env("NO_LAUNCHD"):
        return False, t("job_unsupported")
    os.makedirs(path("logs"), exist_ok=True)
    data = {
        "Label": label(),
        "ProgramArguments": [python_path(), script, "tick"],
        "RunAtLoad": True,
        "StartCalendarInterval": [{"Minute": 7}],
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"},
        "StandardOutPath": path("logs", "launchd.log"),
        "StandardErrorPath": path("logs", "launchd.log"),
        "ProcessType": "Background",
        "LowPriorityIO": True,
    }
    if env("HOME"):
        data["EnvironmentVariables"]["SESSION_RELAY_HOME"] = env("HOME")
    if job_loaded():
        launchctl("bootout", "%s/%s" % (domain(), label()))
    os.makedirs(os.path.dirname(plist_path()), exist_ok=True)
    with open(plist_path(), "wb") as f:
        plistlib.dump(data, f)
    done = launchctl("bootstrap", domain(), plist_path())
    if done.returncode != 0:
        return False, t("job_fail", e=done.stderr.strip())
    return True, t("job_ok")


def remove_job():
    """Removes the plist first, then unloads. Unloading kills this process if the job is running it, so it is last."""
    try:
        os.unlink(plist_path())
    except OSError:
        pass
    if job_loaded():
        launchctl("bootout", "%s/%s" % (domain(), label()))


def stop(reason, detail=""):
    """Stops calling the server from this computer. The record of what was sent stays."""
    state = load_state()
    state["stopped"] = {"at": now_utc().isoformat(), "reason": reason, "detail": detail}
    save_state(state)
    log("stopped: %s %s" % (reason, detail))
    say(t("stopped", reason=reason_text(reason), detail=detail))
    remove_job()


def locally_expired(cfg):
    end = parse_time(cfg.get("expires_at"))
    return end is not None and now_utc() >= end


# ---------- Sync ----------

@contextlib.contextmanager
def lock():
    """One sync at a time. A lock older than STALE_LOCK is from a run that died and is taken over."""
    p = path(".lock")
    os.makedirs(home(), exist_ok=True)
    try:
        if time.time() - os.path.getmtime(p) > STALE_LOCK:
            os.unlink(p)
    except OSError:
        pass
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        yield False
        return
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield True
    finally:
        with contextlib.suppress(OSError):
            os.unlink(p)


def upload(cfg, entry, day, piece, cwd):
    body = gzip.compress(piece["data"], 6)
    if len(body) > MAX_SLICE_GZ:
        raise ValueError("slice too large (%d MB compressed)" % (len(body) // 2 ** 20))
    meta = {"cwd": cwd, "lines": piece["lines"], "first": piece["first"], "last": piece["last"],
            "sha256": piece["sha256"], "bytes": len(piece["data"]), "media_removed": piece.get("media", 0),
            "media_stripped": 1, "secrets_redacted": piece.get("secrets", 0), "redacted": redact.VERSION}
    route = "/v1/sessions/%s/%s/%s" % (day, entry["tool"], urllib.parse.quote(entry["session_id"]))
    request(cfg, "PUT", route, body, {
        "Content-Type": "application/x-ndjson",
        "Content-Encoding": "gzip",
        "X-Relay-Meta": json.dumps(meta, ensure_ascii=True),
    })
    return len(body)


def sync(cfg, reason):
    """Uploads every slice that is new or changed. Returns a result dict; raises ServerError on refusal."""
    me = check_code(cfg)
    if me.get("expires_at") != cfg.get("expires_at"):
        cfg["expires_at"] = me.get("expires_at")
        save_config(cfg)

    state = load_state()
    epoch = me.get("epoch", 1)
    if state.get("epoch", 1) != epoch:
        # The server lost this user's files or the admin asked for them again: forget what was sent.
        log("server asked for a full resend (epoch %s -> %s)" % (state.get("epoch", 1), epoch))
        state["slices"] = {}
        state["files"] = {}
    state["epoch"] = epoch
    if state.get("redact_version") != redact.VERSION:
        # New masking rules (or a client from before masking): read every session again. Slices that come out
        # different are sent again and overwrite the server's copy; the others match their stored hash and stay.
        state["files"] = {}
        state["redact_version"] = redact.VERSION
    files = state.setdefault("files", {})
    sent = state.setdefault("slices", {})
    result = {"started_at": now_utc().isoformat(), "reason": reason, "sessions": 0, "slices": 0,
              "bytes": 0, "skipped_automated": 0, "errors": []}
    entries = sources.find_session_files()
    try:
        sync_files(cfg, entries, files, sent, state, result)
    finally:
        save_state(state)  # Keep what was sent even when the run is cut short.
    result["finished_at"] = now_utc().isoformat()
    state["last_sync_date"] = today()
    state["last_sync_at"] = result["finished_at"]
    state["last_result"] = result
    save_state(state)
    try:
        request(cfg, "POST", "/v1/sync", json.dumps(result).encode(), {"Content-Type": "application/json"})
    except (ServerError, OSError):
        pass  # Only a report for the admin page.
    return result


def sync_files(cfg, entries, files, sent, state, result):
    since_save = 0
    for i, entry in enumerate(entries):
        try:
            st = os.stat(entry["path"])
        except OSError:
            continue
        stamp = [st.st_size, int(st.st_mtime)]
        if files.get(entry["path"]) == stamp:
            continue
        try:
            parsed = sources.read_slices(entry)
        except OSError as e:
            result["errors"].append("%s: %s" % (entry["path"], e))
            continue
        if parsed["automated"]:
            result["skipped_automated"] += 1
            files[entry["path"]] = stamp
            continue
        key = "%s:%s" % (entry["tool"], entry["session_id"])
        done = sent.setdefault(key, {})
        complete = True
        uploaded_any = False
        for day in sorted(parsed["days"]):
            piece = parsed["days"][day]
            if done.get(day) == piece["sha256"]:
                continue
            try:
                result["bytes"] += upload(cfg, entry, day, piece, parsed["cwd"])
            except ValueError as e:
                result["errors"].append("%s %s: %s" % (key, day, e))
                complete = False
                continue
            except ServerError as e:
                if e.status not in (400, 413):
                    raise
                result["errors"].append("%s %s: %s" % (key, day, e))
                complete = False
                continue
            done[day] = piece["sha256"]
            result["slices"] += 1
            uploaded_any = True
            since_save += 1
        if uploaded_any:
            result["sessions"] += 1
        if complete:
            files[entry["path"]] = stamp
        if since_save >= SAVE_EVERY:
            save_state(state)
            since_save = 0
            log("progress %d/%d files, %d slices" % (i + 1, len(entries), result["slices"]))


def run_sync(reason):
    cfg = load_config()
    if not cfg.get("code"):
        say(t("not_setup"))
        return 2
    state = load_state()
    if state.get("stopped"):
        say(t("is_stopped", date=state["stopped"]["at"][:10], reason=reason_text(state["stopped"]["reason"])))
        return 2
    if locally_expired(cfg):
        stop("expired", t("ended_at", end=cfg.get("expires_at")))
        return 3
    with lock() as got:
        if not got:
            say(t("busy"))
            return 0
        try:
            result = sync(cfg, reason)
        except ServerError as e:
            why = ended_reason(e)
            if why:
                stop(why, str(e.body.get("error") or ""))
                return 3
            log("server error: %s" % e)
            say(t("server_retry", e=e))
            return 1
        except (OSError, urllib.error.URLError) as e:
            log("network error: %s" % e)
            say(t("net_retry", e=e))
            return 1
    msg = t("synced", slices=result["slices"], sessions=result["sessions"], mb=result["bytes"] / 1e6)
    if result["errors"]:
        msg += t("sync_errors", n=len(result["errors"]))
    log(msg)
    say(msg)
    return 0


# ---------- Commands ----------

def cmd_init(args):
    server = (args.server or env("SERVER") or load_config().get("server") or defaults().get("server_url") or "").strip()
    if not server:
        say(t("no_server"))
        return 2
    code = normalize_code(args.code)
    cfg = {"server": server, "code": code}
    try:
        me = check_code(cfg)
    except ServerError as e:
        if e.status == 401:
            say(t("code_invalid"))
        elif ended_reason(e):
            say(t("code_ended", end=(e.body.get("expires_at") or "")[:10]))
        else:
            say(t("refused", e=e))
        return 2
    except (OSError, urllib.error.URLError) as e:
        say(t("unreachable", server=server, e=e))
        return 1
    cfg.update({"user_id": me.get("user_id"), "phone_hint": me.get("phone_hint"), "expires_at": me.get("expires_at"),
                "activated_at": now_utc().isoformat(), "hostname": os.uname().nodename})
    previous = load_config()
    save_config(cfg)
    state = load_state()
    if previous.get("user_id") and previous.get("user_id") != cfg["user_id"]:
        state = {}  # A different user: what was sent before went to the other user's folder.
    state.pop("stopped", None)
    save_state(state)
    log("init ok user=%s expires=%s" % (cfg["user_id"], cfg["expires_at"]))
    end = local_date(cfg["expires_at"]) or t("never")
    say(t("confirmed", user=cfg.get("phone_hint") or cfg["user_id"], end=end))
    say(t("notice"))
    found = sources.find_session_files()
    say(t("found", n=len(found), c=sum(1 for f in found if f["tool"] == "claude"),
          x=sum(1 for f in found if f["tool"] == "codex")))
    copy_app()
    if not args.no_skill and install_skill():
        say(t("skill"))
    if args.no_job:
        say(t("no_job"))
        say(t("commands"))
        return run_sync("init") if args.foreground else 0
    ok, msg = install_job()
    say(msg)
    say(t("commands"))
    if ok and not args.foreground:
        say(t("bg"))
        return 0
    say(t("fg"))
    return run_sync("init")


def local_date(text):
    moment = parse_time(text)
    return moment.astimezone().date().isoformat() if moment else None


def cmd_tick(args):
    cfg = load_config()
    state = load_state()
    if not cfg.get("code") or state.get("stopped"):
        remove_job()  # Nothing to do on this computer; make sure the job is gone.
        return 0
    if locally_expired(cfg):
        stop("expired", t("ended_at", end=cfg.get("expires_at")))
        return 0
    if state.get("last_sync_date") == today():
        return 0  # Once a day.
    return run_sync("daily")


def cmd_sync(args):
    return run_sync("manual")


def cmd_status(args):
    cfg = load_config()
    state = load_state()
    last = state.get("last_result") or {}
    info = {
        "configured": bool(cfg.get("code")),
        "server": cfg.get("server"),
        "user": cfg.get("phone_hint") or cfg.get("user_id"),
        "expires_at": cfg.get("expires_at"),
        "stopped": state.get("stopped"),
        "job_loaded": job_loaded(),
        "running": os.path.exists(path(".lock")),
        "last_sync_date": state.get("last_sync_date"),
        "last_sync_at": state.get("last_sync_at"),
        "last_result": {k: last.get(k) for k in ("reason", "sessions", "slices", "bytes", "skipped_automated")},
        "last_errors": (last.get("errors") or [])[:5],
        "sessions_sent": len(state.get("slices") or {}),
        "slices_sent": sum(len(v) for v in (state.get("slices") or {}).values()),
        "data_dir": home(),
    }
    try:
        with open(path("logs", "relay.log"), encoding="utf-8") as f:
            info["recent_log"] = [line.rstrip() for line in f.readlines()[-8:]]
    except OSError:
        info["recent_log"] = []
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    if not info["configured"]:
        say(t("not_setup"))
        return 0
    say(t("st.user", user=info["user"], server=info["server"]))
    say(t("st.end", end=local_date(info["expires_at"]) or t("never")))
    if info["stopped"]:
        say(t("st.stopped", at=info["stopped"]["at"][:16], reason=reason_text(info["stopped"]["reason"])))
    say(t("st.job", on=t("st.on") if info["job_loaded"] else t("st.off"), running=t("st.running") if info["running"] else ""))
    say(t("st.last", at=(info["last_sync_at"] or "-")[:16], detail=json.dumps(info["last_result"])))
    say(t("st.sent", slices=info["slices_sent"], sessions=info["sessions_sent"]))
    for e in info["last_errors"]:
        say(t("st.error", e=e))
    for line in info["recent_log"]:
        print("  " + line)
    return 0


def cmd_stop(args):
    stop("stopped by user")
    return 0


def cmd_uninstall(args):
    if load_config().get("code") and not load_state().get("stopped"):
        stop("stopped by user")
    else:
        remove_job()
    removed = []
    for target in skill_targets():
        if os.path.exists(os.path.join(target, "SKILL.md")):
            shutil.rmtree(target, ignore_errors=True)
            removed.append(target)
    shutil.rmtree(home(), ignore_errors=True)
    removed.append(home())
    say(t("uninstalled", paths=", ".join(removed)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="relay", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--code", required=True)
    p.add_argument("--server")
    p.add_argument("--foreground", action="store_true", help="upload now instead of in the background")
    p.add_argument("--no-job", action="store_true", help="do not register the daily job")
    p.add_argument("--no-skill", action="store_true", help="do not install the Claude Code / Codex skill")
    sub.add_parser("tick")
    sub.add_parser("sync")
    p = sub.add_parser("status")
    p.add_argument("--json", action="store_true")
    sub.add_parser("stop")
    sub.add_parser("uninstall")
    args = parser.parse_args(argv)
    commands = {"init": cmd_init, "tick": cmd_tick, "sync": cmd_sync, "status": cmd_status, "stop": cmd_stop,
                "uninstall": cmd_uninstall}
    return commands[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

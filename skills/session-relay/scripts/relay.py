#!/usr/bin/env python3
"""session-relay: sends this computer's Claude Code and Codex conversations to the relay server, once a day.

Standard library only, Python 3.9+ (the python3 that ships with macOS).

  init --code CODE   Check the code with the server, save it, register the daily job and start the first upload.
  tick               What the daily job runs (at login and every hour). Syncs at most once a day.
  sync               Sync now, in the foreground, even if today was already synced.
  status [--json]    Show the state.
  stop               Stop for good on this computer: remove the job and stop calling the server.

Nothing is sent twice. Each session is split into one slice per local date (a session used across midnight gives
two slices) and the sha256 of every uploaded slice is kept. A slice is sent again only when it changed, which is
what happens to "today" when it is synced in the morning and the session goes on in the afternoon.

When the code's end time has passed, the job stops itself without calling the server. When the server says the
code has ended (or no longer exists), it stops the same way.
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
import sources  # noqa: E402

VERSION = "0.1.0"
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
    """The skill folder can move or update, so the job runs from a copy in ~/.session-relay/app."""
    src = os.path.dirname(os.path.abspath(__file__))
    dest = path("app")
    if os.path.abspath(src) != os.path.abspath(dest):
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "test_*"))
    return os.path.join(dest, "relay.py")


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
    script = copy_app()
    if sys.platform != "darwin" or env("NO_LAUNCHD"):
        return False, "The daily job can only be registered on macOS for now. Run `relay.py tick` once a day."
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
        return False, "Could not register the job: %s" % done.stderr.strip()
    return True, "Registered the daily job (%s)." % label()


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
    say("Stopped (%s). This computer no longer calls the server. %s" % (reason, detail))
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
            "sha256": piece["sha256"], "bytes": len(piece["data"])}
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
        say("Not set up yet. Run init with the code first.")
        return 2
    state = load_state()
    if state.get("stopped"):
        say("Stopped on %s (%s). Run init again to start." % (state["stopped"]["at"][:10], state["stopped"]["reason"]))
        return 2
    if locally_expired(cfg):
        stop("expired", "The code ended at %s." % cfg.get("expires_at"))
        return 3
    with lock() as got:
        if not got:
            say("Another sync is running.")
            return 0
        try:
            result = sync(cfg, reason)
        except ServerError as e:
            why = ended_reason(e)
            if why:
                stop(why, str(e.body.get("error") or ""))
                return 3
            log("server error: %s" % e)
            say("Server error, will retry later: %s" % e)
            return 1
        except (OSError, urllib.error.URLError) as e:
            log("network error: %s" % e)
            say("Could not reach the server, will retry later: %s" % e)
            return 1
    msg = "Synced: %d slices from %d sessions, %.1f MB compressed." % (
        result["slices"], result["sessions"], result["bytes"] / 1e6)
    if result["errors"]:
        msg += " %d errors (see status)." % len(result["errors"])
    log(msg)
    say(msg)
    return 0


# ---------- Commands ----------

def cmd_init(args):
    server = (args.server or env("SERVER") or load_config().get("server") or defaults().get("server_url") or "").strip()
    if not server:
        say("No server address. Pass --server https://... (the admin gives it with the code).")
        return 2
    code = normalize_code(args.code)
    cfg = {"server": server, "code": code}
    try:
        me = check_code(cfg)
    except ServerError as e:
        if e.status == 401:
            say("This code is not valid. Check it and try again.")
        elif ended_reason(e):
            say("This code has already ended (%s)." % e.body.get("expires_at", ""))
        else:
            say("The server refused: %s" % e)
        return 2
    except (OSError, urllib.error.URLError) as e:
        say("Could not reach the server %s: %s" % (server, e))
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
    say("Code confirmed. User %s, ends %s." % (cfg.get("phone_hint") or cfg["user_id"], cfg["expires_at"] or "never"))
    found = sources.find_session_files()
    say("Found %d session files (Claude Code %d, Codex %d)." % (
        len(found), sum(1 for f in found if f["tool"] == "claude"), sum(1 for f in found if f["tool"] == "codex")))
    if args.foreground:
        say(install_job()[1] if not args.no_job else "No daily job (--no-job).")
        return run_sync("init")
    if args.no_job:
        say("No daily job (--no-job). Run sync to upload.")
        return 0
    ok, msg = install_job()
    say(msg)
    if ok:
        say("The first upload is running in the background. Check it with status.")
        return 0
    say("Uploading now in the foreground.")
    return run_sync("init")


def cmd_tick(args):
    cfg = load_config()
    state = load_state()
    if not cfg.get("code") or state.get("stopped"):
        remove_job()  # Nothing to do on this computer; make sure the job is gone.
        return 0
    if locally_expired(cfg):
        stop("expired", "The code ended at %s." % cfg.get("expires_at"))
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
        say("Not set up. Run init with the code.")
        return 0
    say("User: %s  Server: %s" % (info["user"], info["server"]))
    say("Ends: %s" % (info["expires_at"] or "never"))
    if info["stopped"]:
        say("Stopped: %s (%s)" % (info["stopped"]["at"], info["stopped"]["reason"]))
    say("Daily job: %s%s" % ("on" if info["job_loaded"] else "off", ", syncing now" if info["running"] else ""))
    say("Last sync: %s  (%s)" % (info["last_sync_at"] or "never", json.dumps(info["last_result"])))
    say("Sent so far: %d slices from %d sessions" % (info["slices_sent"], info["sessions_sent"]))
    for e in info["last_errors"]:
        say("error: %s" % e)
    for line in info["recent_log"]:
        print("  " + line)
    return 0


def cmd_stop(args):
    stop("stopped by user")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="relay.py", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--code", required=True)
    p.add_argument("--server")
    p.add_argument("--foreground", action="store_true", help="upload now instead of in the background")
    p.add_argument("--no-job", action="store_true", help="do not register the daily job")
    sub.add_parser("tick")
    sub.add_parser("sync")
    p = sub.add_parser("status")
    p.add_argument("--json", action="store_true")
    sub.add_parser("stop")
    args = parser.parse_args(argv)
    return {"init": cmd_init, "tick": cmd_tick, "sync": cmd_sync, "status": cmd_status, "stop": cmd_stop}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

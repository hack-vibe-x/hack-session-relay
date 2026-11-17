#!/usr/bin/env python3
"""session-relay server. Standard library only (Python 3.10+). Runs on Railway with a volume.

Storage (DATA_DIR, the Railway volume):
  users.json                                  one record per code: phone, sha256 of the code, end time
                                              (read once at start and kept in memory; rewritten on every change)
  users/<user id>/<YYYY-MM-DD>/<tool>_<session>.jsonl.gz      one session's lines for that local date
  users/<user id>/<YYYY-MM-DD>/<tool>_<session>.meta.json     project folder, line count, first/last time
  index.db                                    SQLite index of those files (store.py); rebuilt from them when missing

Client API (Authorization: Bearer <code>):
  GET  /v1/me                                 is the code valid; its end time
  PUT  /v1/sessions/<date>/<tool>/<session>   upload one day of one session (gzip body); replaces the earlier copy
  POST /v1/batch                              many such slices in one request (format below), optionally with the
                                              sync report; answers one result per slice, in order
  POST /v1/sync                               report of a finished sync
  A batch body: b"SRB1\n", one line of JSON {"slices": [{"date", "tool", "session_id", "size", "meta"}, ...],
  "report": {...} or absent}, then the slices' gzip bodies back to back, each "size" bytes long.
  An ended code gets 403 {"status": "expired"}; an unknown code 401 {"status": "invalid"}.

Admin API (Authorization: Bearer <ADMIN_KEY>):
  GET   /admin/overview                       everything the admin page opens with, in one answer: every user with
                                              totals and dates, and the client release. ETag: If-None-Match gets
                                              304 when nothing changed since. Every JSON answer is gzip on request.
  GET   /admin/users                          every user with totals and dates
  POST  /admin/users {phone, expires_at, memo}   issue a code; the code is only in this response
  PATCH /admin/users/<id> {expires_at, memo, resend}  change the end time ("now" ends it now); resend: true asks
                                              the user's computer to send everything again at its next sync
  GET   /admin/users/<id>/days                dates with uploads
  GET   /admin/users/<id>/days/<date>         sessions of one date, each with "dates": every date it appears on
  GET   /admin/users/<id>/download?from=&to=  zip of the dates in the range (one date: from=to)
  GET   /admin/client                         the client release offered to computers
  PUT   /admin/client {version, ref, files}   offer a release: version, a 40-hex commit of the GitHub repository
                                              and {path: sha256} for its files (scripts/release.py sends this)
"""
import datetime
import gzip
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import media
import store

DATA_DIR = os.environ.get("DATA_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "./data"
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
PORT = int(os.environ.get("PORT", "8080"))
# Local runs stay on this computer. On Railway (and in the Docker image, which sets HOST) it listens on all
# interfaces so the platform's proxy can reach it.
HOST = os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("RAILWAY_ENVIRONMENT") else "127.0.0.1")
MAX_UPLOAD = 100 * 1024 * 1024
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"  # No 0/O, 1/I/L, U: easy to read out and type.
DATE = re.compile(r"^\d{4}-\d\d-\d\d$")
SESSION = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
USER_ID = re.compile(r"^u_[0-9a-f]{10}$")
TOOLS = ("claude", "codex")
RELEASE_FILE = re.compile(r"^(client/[a-z_]+\.(?:py|json)|skill/SKILL\.md)$")
CLIENT_AGENT = re.compile(r"session-relay/([0-9]+(?:\.[0-9]+)*)")

_lock = threading.Lock()
_lock_rev = threading.Lock()
_files_lock = threading.Lock()  # Uploads and the image cleanup never write the same session file at once.
_failures = {}  # ip -> [count, first time]; slows down guessing codes.
_users = None  # users.json in memory: {"by_id": {...}, "by_hash": {code sha256: id}}
INDEX = None  # store.Index, opened in main()
# Changes on every write (user, upload, release). With the start's random part it is the overview's ETag.
_rev = [secrets.token_hex(4), 0]


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def iso(moment):
    return moment.astimezone(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(text):
    if text in (None, ""):
        return None
    if text == "now":
        return now()
    moment = datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment


def normalize_code(code):
    return "".join(ch for ch in code.upper() if ch.isalnum())


def code_hash(code):
    return hashlib.sha256(normalize_code(code).encode()).hexdigest()


def new_code():
    body = "".join(secrets.choice(CODE_ALPHABET) for _ in range(16))
    return "SR-" + "-".join(body[i:i + 4] for i in range(0, 16, 4))


def phone_hint(phone):
    digits = re.sub(r"\D", "", phone)
    return "***-" + digits[-4:] if len(digits) >= 4 else "***"


# ---------- Store ----------

def release_file():
    return os.path.join(DATA_DIR, "client.json")


def load_release():
    try:
        with open(release_file(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def users_file():
    return os.path.join(DATA_DIR, "users.json")


def user_dir(uid):
    return os.path.join(DATA_DIR, "users", uid)


def bump():
    with _lock_rev:
        _rev[1] += 1


def etag():
    return '"%s.%d"' % (_rev[0], _rev[1])


def _remember(users):
    global _users
    _users = {"by_id": users, "by_hash": {u["code_sha256"]: uid for uid, u in users.items()}}


def load_users():
    """A copy of every user; change it and pass it to save_users. Only this process writes users.json."""
    if _users is None:
        try:
            with open(users_file(), encoding="utf-8") as f:
                _remember(json.load(f))
        except FileNotFoundError:
            _remember({})
    return json.loads(json.dumps(_users["by_id"]))


def save_users(users):
    write_atomic(users_file(), json.dumps(users, ensure_ascii=False, indent=1).encode())
    _remember(json.loads(json.dumps(users)))
    bump()


def write_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def status_of(user):
    end = parse_time(user.get("expires_at"))
    return "expired" if end and now() >= end else "active"


def find_by_code(code):
    load_users()
    uid = _users["by_hash"].get(code_hash(code))  # A dict lookup on the hash: no comparison of the code itself.
    return (uid, load_users()[uid]) if uid else (None, None)


def days_of(uid):
    return INDEX.days(uid).get(uid, [])


def public_user(uid, user, days=None):
    out = {k: v for k, v in user.items() if k != "code_sha256"}
    out["id"] = uid
    out["status"] = status_of(user)
    days = days_of(uid) if days is None else days
    out["days"] = days
    out["days_count"] = len(days)
    out["sessions_total"] = sum(d["sessions"] for d in days)
    out["bytes_total"] = sum(d["bytes"] for d in days)
    out["last_day"] = days[0]["date"] if days else None
    return out


# ---------- HTTP ----------

class Handler(BaseHTTPRequestHandler):
    server_version = "session-relay"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def client_ip(self):
        return (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()

    def send_json(self, status, data, headers=None):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if len(body) > 1400 and "gzip" in (self.headers.get("Accept-Encoding") or ""):
            body = gzip.compress(body, 6)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self, limit):
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            raise ValueError("too large")
        return self.rfile.read(length) if length else b""

    def read_json(self):
        raw = self.read_body(1024 * 1024)
        return json.loads(raw) if raw else {}

    def bearer(self):
        auth = self.headers.get("Authorization", "")
        return auth[7:].strip() if auth.startswith("Bearer ") else ""

    def route(self, method):
        url = urlparse(self.path)
        parts = [unquote(p) for p in url.path.strip("/").split("/") if p]
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if parts == ["health"]:
                return self.send_json(200, {"ok": True})
            if parts[:1] == ["v1"]:
                return self.client_api(method, parts[1:])
            if parts[:1] == ["admin"]:
                if not ADMIN_KEY or not hmac.compare_digest(self.bearer().encode(), ADMIN_KEY.encode()):
                    return self.send_json(401, {"error": "admin key required"})
                return self.admin_api(method, parts[1:], query)
            return self.send_json(404, {"error": "not found"})
        except ValueError as e:
            return self.send_json(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            sys.stderr.write("error: %r\n" % e)
            return self.send_json(500, {"error": "server error"})

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PUT(self):
        self.route("PUT")

    def do_PATCH(self):
        self.route("PATCH")

    # ----- client -----

    def client_api(self, method, parts):
        ip = self.client_ip()
        count, since = _failures.get(ip, [0, time.time()])
        if time.time() - since > 600:
            count, since = 0, time.time()
        if count >= 20:
            return self.send_json(429, {"error": "too many attempts, try again in 10 minutes"})
        uid, user = find_by_code(self.bearer()) if self.bearer() else (None, None)
        if not user:
            _failures[ip] = [count + 1, since]
            self.close_connection = True  # Do not read an upload from an unknown sender.
            return self.send_json(401, {"status": "invalid", "error": "unknown code"})
        if status_of(user) != "active":
            self.close_connection = True
            return self.send_json(403, {"status": "expired", "expires_at": user.get("expires_at"),
                                        "error": "this code has ended"})

        if method == "GET" and parts == ["me"]:
            agent = CLIENT_AGENT.search(self.headers.get("User-Agent") or "")
            with _lock:
                users = load_users()
                users[uid]["last_seen_at"] = iso(now())
                if agent:
                    users[uid]["client_version"] = agent.group(1)
                if not users[uid].get("activated_at"):
                    users[uid]["activated_at"] = iso(now())
                save_users(users)
            # epoch: raised when the server lost or dropped this user's files; clients then send everything again.
            return self.send_json(200, {"status": "active", "user_id": uid, "phone_hint": phone_hint(user["phone"]),
                                        "expires_at": user.get("expires_at"), "epoch": user.get("epoch", 1),
                                        "client": load_release(), "server_time": iso(now())})

        if method == "PUT" and len(parts) == 4 and parts[0] == "sessions":
            _, day, tool, sid = parts
            if not slice_path_ok(day, tool, sid):
                self.close_connection = True
                raise ValueError("bad path")
            try:
                body = self.read_body(MAX_UPLOAD)
            except ValueError:
                self.close_connection = True
                return self.send_json(413, {"error": "upload too large"})
            try:
                meta = json.loads(self.headers.get("X-Relay-Meta") or "{}")
            except ValueError:
                meta = {}
            store_slice(uid, day, tool, sid, body, meta)
            return self.send_json(200, {"ok": True})

        if method == "POST" and parts == ["batch"]:
            try:
                body = self.read_body(MAX_UPLOAD)
            except ValueError:
                self.close_connection = True
                return self.send_json(413, {"error": "upload too large"})
            head, _, rest = body.partition(b"\n")
            line, _, rest = rest.partition(b"\n")
            if head != b"SRB1":
                raise ValueError("not a batch")
            manifest = json.loads(line)
            items = manifest.get("slices") if isinstance(manifest, dict) else None
            if not isinstance(items, list):
                raise ValueError("batch has no slices list")
            sizes = [item.get("size") if isinstance(item, dict) else None for item in items]
            if not all(isinstance(n, int) and n >= 0 for n in sizes) or sum(sizes) != len(rest):
                raise ValueError("batch sizes do not match its body")
            results, offset = [], 0
            for item, size in zip(items, sizes):
                piece, offset = rest[offset:offset + size], offset + size
                day, tool, sid = str(item.get("date")), str(item.get("tool")), str(item.get("session_id"))
                try:
                    if not slice_path_ok(day, tool, sid):
                        raise ValueError("bad path")
                    store_slice(uid, day, tool, sid, piece, item.get("meta") or {})
                    results.append({"ok": True})
                except ValueError as e:  # One bad slice does not stop the others.
                    results.append({"ok": False, "status": 400, "error": str(e)})
            if isinstance(manifest, dict) and isinstance(manifest.get("report"), dict):
                record_sync(uid, manifest["report"])
            return self.send_json(200, {"results": results})

        if method == "POST" and parts == ["sync"]:
            record_sync(uid, self.read_json())
            return self.send_json(200, {"ok": True})

        return self.send_json(404, {"error": "not found"})

    # ----- admin -----

    def admin_api(self, method, parts, query):
        if parts == ["client"] and method == "GET":
            return self.send_json(200, {"client": load_release()})

        if parts == ["client"] and method == "PUT":
            data = self.read_json()
            version, ref, files = str(data.get("version") or ""), str(data.get("ref") or ""), data.get("files")
            if not re.match(r"^[0-9]+(\.[0-9]+)*$", version) or not re.match(r"^[0-9a-f]{40}$", ref):
                raise ValueError("version (like 0.6.0) and a 40-character commit ref are required")
            if not isinstance(files, dict) or "client/relay.py" not in files or any(
                    not RELEASE_FILE.match(k) or not re.match(r"^[0-9a-f]{64}$", str(v)) for k, v in files.items()):
                raise ValueError("files must map client/*.py, client/*.json and skill/SKILL.md to sha256")
            release = {"version": version, "ref": ref, "files": files, "released_at": iso(now())}
            write_atomic(release_file(), json.dumps(release, indent=1).encode())
            bump()
            return self.send_json(200, {"client": release})

        if parts in (["users"], ["overview"]) and method == "GET":
            tag = etag()  # Taken before reading: a write during the read makes the next request fetch again.
            if parts == ["overview"] and self.headers.get("If-None-Match") == tag:
                self.send_response(304)
                self.send_header("ETag", tag)
                self.send_header("Content-Length", "0")
                return self.end_headers()
            days = INDEX.days()
            listed = [public_user(uid, u, days.get(uid, [])) for uid, u in load_users().items()]
            listed.sort(key=lambda u: u.get("created_at") or "", reverse=True)
            if parts == ["users"]:
                return self.send_json(200, {"users": listed})
            return self.send_json(200, {"users": listed, "client": load_release(), "rev": tag,
                                        "server_time": iso(now())}, {"ETag": tag})

        if parts == ["users"] and method == "POST":
            data = self.read_json()
            phone = str(data.get("phone") or "").strip()
            if len(re.sub(r"\D", "", phone)) < 8:
                raise ValueError("phone number required")
            end = parse_time(data.get("expires_at"))
            if end is None:
                raise ValueError("expires_at required")
            code = new_code()
            uid = "u_" + secrets.token_hex(5)
            with _lock:
                users = load_users()
                users[uid] = {"phone": phone, "code_sha256": code_hash(code), "code_hint": code[-4:],
                              "memo": str(data.get("memo") or ""), "created_at": iso(now()), "expires_at": iso(end)}
                save_users(users)
            os.makedirs(user_dir(uid), exist_ok=True)
            return self.send_json(201, {"user": public_user(uid, users[uid]), "code": code})

        if len(parts) >= 2 and parts[0] == "users":
            uid = parts[1]
            users = load_users()
            if not USER_ID.match(uid) or uid not in users:
                return self.send_json(404, {"error": "no such user"})
            rest = parts[2:]
            if not rest and method == "GET":
                return self.send_json(200, {"user": public_user(uid, users[uid])})
            if not rest and method == "PATCH":
                data = self.read_json()
                with _lock:
                    users = load_users()
                    if "expires_at" in data:
                        end = parse_time(data["expires_at"])
                        if end is None:
                            raise ValueError("expires_at required")
                        users[uid]["expires_at"] = iso(end)
                    if "memo" in data:
                        users[uid]["memo"] = str(data["memo"])
                    if data.get("resend"):
                        users[uid]["epoch"] = users[uid].get("epoch", 1) + 1  # Next sync sends everything again.
                    save_users(users)
                return self.send_json(200, {"user": public_user(uid, users[uid])})
            if rest == ["days"] and method == "GET":
                return self.send_json(200, {"days": days_of(uid)})
            if len(rest) == 2 and rest[0] == "days" and DATE.match(rest[1]) and method == "GET":
                return self.send_json(200, {"sessions": sessions_of(uid, rest[1])})
            if rest == ["download"] and method == "GET":
                return self.send_zip(uid, users[uid], query)
        return self.send_json(404, {"error": "not found"})

    def send_zip(self, uid, user, query):
        start, end = query.get("from"), query.get("to") or query.get("from")
        if not (start and DATE.match(start) and end and DATE.match(end)):
            raise ValueError("from and to dates required")
        days = [d["date"] for d in days_of(uid) if start <= d["date"] <= end]
        if not days:
            return self.send_json(404, {"error": "no sessions in that range"})
        folder = re.sub(r"\D", "", user["phone"]) or uid
        spool = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
        with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for day in sorted(days):
                base = os.path.join(user_dir(uid), day)
                index = []
                for name in sorted(os.listdir(base)):
                    if not name.endswith(".jsonl.gz"):
                        continue
                    with gzip.open(os.path.join(base, name)) as src, zf.open("%s/%s/%s" % (folder, day, name[:-3]), "w") as dst:
                        shutil.copyfileobj(src, dst, 1024 * 1024)
                    try:
                        with open(os.path.join(base, name[:-len(".jsonl.gz")] + ".meta.json"), encoding="utf-8") as f:
                            index.append(json.load(f))
                    except (OSError, ValueError):
                        pass
                zf.writestr("%s/%s/_index.json" % (folder, day), json.dumps(index, ensure_ascii=False, indent=1))
        size = spool.tell()
        spool.seek(0)
        label = start if start == end else "%s_%s" % (start, end)
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", 'attachment; filename="sessions_%s_%s.zip"' % (folder, label))
        self.end_headers()
        shutil.copyfileobj(spool, self.wfile, 1024 * 1024)
        spool.close()


def slice_path_ok(day, tool, sid):
    return bool(DATE.match(day)) and tool in TOOLS and bool(SESSION.match(sid))


def store_slice(uid, day, tool, sid, body, meta):
    """Writes one day of one session (gzip JSONL), replacing the earlier copy. ValueError when it is not gzip."""
    if body[:2] != b"\x1f\x8b":
        raise ValueError("body must be gzip")
    meta = {k: meta.get(k) for k in ("cwd", "lines", "first", "last", "sha256", "bytes", "media_removed",
                                     "media_stripped", "secrets_redacted", "redacted")}
    if meta.get("media_stripped") != media.VERSION:
        # An older client: replace images here.
        try:
            body, raw_bytes, removed = strip_gz(body)
        except (OSError, EOFError, ValueError):
            raise ValueError("body is not valid gzip")
        meta.update({"bytes": raw_bytes, "media_removed": removed, "media_stripped": media.VERSION})
    folder = os.path.join(user_dir(uid), day)
    meta.update({"tool": tool, "session_id": sid, "uploaded_at": iso(now()), "gz_bytes": len(body)})
    data_path = os.path.join(folder, "%s_%s.jsonl.gz" % (tool, sid))
    with _files_lock:
        write_atomic(data_path, body)
        write_atomic(os.path.join(folder, "%s_%s.meta.json" % (tool, sid)), json.dumps(meta).encode())
        INDEX.put(uid, day, tool, sid, meta, len(body), os.stat(data_path).st_mtime)
    bump()


def record_sync(uid, report):
    with _lock:
        users = load_users()
        users[uid]["last_sync_at"] = iso(now())
        users[uid]["last_sync"] = {k: report.get(k) for k in ("reason", "sessions", "slices", "bytes",
                                                               "client_version")}
        if report.get("client_version"):
            users[uid]["client_version"] = str(report["client_version"])[:20]
        save_users(users)


def sessions_of(uid, day):
    return INDEX.sessions(uid, day)


def strip_gz(body):
    """gzip JSONL -> (gzip JSONL with images replaced by text notes, uncompressed size, images replaced)."""
    out = io.BytesIO()
    raw_bytes = removed = 0
    with gzip.GzipFile(fileobj=io.BytesIO(body)) as src, gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as dst:
        for line in src:
            if not line.endswith(b"\n"):
                line += b"\n"
            line, n = media.strip_line(line)
            removed += n
            raw_bytes += len(line)
            dst.write(line)
    return out.getvalue(), raw_bytes, removed


def clean_stored_media():
    """Once per file: replace images in files uploaded before the server did it. Runs in the background."""
    base = os.path.join(DATA_DIR, "users")
    done = saved = 0
    for root, _dirs, names in os.walk(base):
        for name in sorted(names):
            if not name.endswith(".meta.json"):
                continue
            meta_path = os.path.join(root, name)
            data_path = meta_path[:-len(".meta.json")] + ".jsonl.gz"
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
                if meta.get("media_stripped") == media.VERSION or not os.path.exists(data_path):
                    continue
                stamp = os.path.getmtime(data_path)
                with open(data_path, "rb") as f:
                    old = f.read()
                new, raw_bytes, removed = strip_gz(old)
                meta.update({"bytes": raw_bytes, "media_removed": removed, "media_stripped": media.VERSION,
                             "gz_bytes": len(new)})
                with _files_lock:
                    if os.path.getmtime(data_path) != stamp:
                        continue  # A new upload arrived meanwhile; it was stripped on the way in.
                    write_atomic(data_path, new)
                    write_atomic(meta_path, json.dumps(meta).encode())
                    day = os.path.basename(root)
                    tool, sid = name[:-len(".meta.json")].split("_", 1)
                    INDEX.put(os.path.basename(os.path.dirname(root)), day, tool, sid, meta, len(new),
                              os.stat(data_path).st_mtime)
                bump()
                done += 1
                saved += len(old) - len(new)
            except Exception as e:  # noqa: BLE001 — one bad file must not stop the rest.
                sys.stderr.write("media cleanup skipped %s: %r\n" % (data_path, e))
    if done:
        sys.stderr.write("media cleanup: %d files, %.1f MB saved\n" % (done, saved / 1e6))


def main():
    if not ADMIN_KEY:
        sys.stderr.write("warning: ADMIN_KEY is not set; the admin API is closed.\n")
    if os.environ.get("RAILWAY_ENVIRONMENT") and not os.path.ismount(DATA_DIR):
        # Without the volume actually mounted, /data is the container's own disk and every deploy wipes it.
        # This happened once: the first container started before the new volume was attached. Refuse to run.
        sys.stderr.write("error: %s is not a mounted volume; refusing to start so nothing is written to the "
                         "container's temporary disk. Attach the volume and deploy again.\n" % DATA_DIR)
        sys.exit(1)
    os.makedirs(DATA_DIR, exist_ok=True)
    global INDEX
    INDEX = store.Index(os.path.join(DATA_DIR, "index.db"))
    started = time.time()
    changed = INDEX.reconcile(os.path.join(DATA_DIR, "users"))  # Before serving, so the first answers are whole.
    sys.stderr.write("index: %d slices updated in %.1fs\n" % (changed, time.time() - started))
    load_users()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.daemon_threads = True
    threading.Thread(target=clean_stored_media, daemon=True).start()
    sys.stderr.write("session-relay server on %s:%d, data in %s\n" % (HOST, PORT, os.path.abspath(DATA_DIR)))
    httpd.serve_forever()


if __name__ == "__main__":
    main()

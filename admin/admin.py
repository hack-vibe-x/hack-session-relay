#!/usr/bin/env python3
"""session-relay admin: a web page on this computer that controls the relay server. Standard library only.

  python3 admin/admin.py            then open http://127.0.0.1:8787

Settings come from admin/config.json ({"server_url": ..., "admin_key": ...}) or the environment variables
SESSION_RELAY_SERVER and SESSION_RELAY_ADMIN_KEY. The admin key never reaches the browser; this program adds it.

Every code issued here is also written to admin/data/codes.json (the server keeps only a hash of it).

The last overview from the server is kept in admin/data/overview.json, so the page draws at once from it and then
asks the server whether anything changed (If-None-Match: one short request, 304 when nothing did).
"""
import gzip
import json
import os
import sys
import datetime
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CODES = os.path.join(DATA, "codes.json")
OVERVIEW = os.path.join(DATA, "overview.json")
HOST = os.environ.get("SESSION_RELAY_ADMIN_HOST", "127.0.0.1")
PORT = int(os.environ.get("SESSION_RELAY_ADMIN_PORT", "8787"))
_lock = threading.Lock()
_overview = {}  # {"server_url", "etag", "fetched_at", "data"}: the last overview, also in OVERVIEW


def config():
    try:
        with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    return {
        "server_url": (os.environ.get("SESSION_RELAY_SERVER") or cfg.get("server_url") or "").rstrip("/"),
        "admin_key": os.environ.get("SESSION_RELAY_ADMIN_KEY") or cfg.get("admin_key") or "",
    }


def load_codes():
    try:
        with open(CODES, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_private(path, data):
    """Only this account can read it: codes and phone numbers."""
    os.makedirs(DATA, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=DATA, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def save_codes(codes):
    save_private(CODES, codes)


def upstream(method, route, body=None, stream=False, headers=None, full=False):
    cfg = config()
    if not cfg["server_url"] or not cfg["admin_key"]:
        raise RuntimeError("admin/config.json 에 server_url 과 admin_key 를 넣어 주세요.")
    req = urllib.request.Request(cfg["server_url"] + "/admin" + route, data=body, method=method)
    req.add_header("Authorization", "Bearer " + cfg["admin_key"])
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if not stream:
        req.add_header("Accept-Encoding", "gzip")
    for name, value in (headers or {}).items():
        req.add_header(name, value)
    res = urllib.request.urlopen(req, timeout=600)
    if stream:
        return res
    with res:
        raw = res.read()
        if res.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        data = json.loads(raw or b"{}")
        return (data, res.headers) if full else data


def cached_overview():
    """The kept overview for the configured server, or None."""
    with _lock:
        if not _overview:
            try:
                with open(OVERVIEW, encoding="utf-8") as f:
                    _overview.update(json.load(f))
            except (OSError, ValueError):
                pass
        if _overview.get("server_url") != config()["server_url"] or "data" not in _overview:
            return None
        return json.loads(json.dumps(_overview))


def keep_overview(entry):
    with _lock:
        _overview.clear()
        _overview.update(entry)
        save_private(OVERVIEW, entry)


def fresh_overview():
    """The server's overview: one conditional request, the kept copy when nothing changed."""
    kept = cached_overview()
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    try:
        data, headers = upstream("GET", "/overview", headers={"If-None-Match": kept["etag"]} if kept else None,
                                 full=True)
    except urllib.error.HTTPError as e:
        if e.code != 304 or not kept:
            raise
        e.close()
        kept["fetched_at"] = stamp
        keep_overview(kept)
        return kept
    entry = {"server_url": config()["server_url"], "etag": headers.get("ETag") or "", "fetched_at": stamp,
             "data": data}
    keep_overview(entry)
    return entry


def edit_kept_user(user, new=False):
    """After issuing or changing a code, the kept overview shows it too (until the next check replaces it)."""
    kept = cached_overview()
    if not kept:
        return
    users = kept["data"]["users"]
    old = next((u for u in users if u["id"] == user["id"]), None)
    record = dict(user)
    record.pop("code", None)
    if old:
        old.update(record)
    elif new:
        users.insert(0, dict(record, days=record.get("days") or []))
    keep_overview(kept)


def with_codes(entry, cached):
    out = dict(entry["data"], cached=cached, fetched_at=entry["fetched_at"])
    codes = load_codes()
    for u in out["users"]:
        u["code"] = (codes.get(u["id"]) or {}).get("code")
    return out


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length)) if length else {}

    def guard(self):
        # Only pages served by this program may call it (blocks other sites from driving it through the browser).
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and urllib.parse.urlparse(origin).netloc != host:
            self.send_json(403, {"error": "origin"})
            return False
        if host.split(":")[0] not in ("127.0.0.1", "localhost"):
            self.send_json(403, {"error": "host"})
            return False
        return True

    def handle_api(self, method):
        if not self.guard():
            return
        url = urllib.parse.urlparse(self.path)
        route = url.path[len("/api"):]
        try:
            if route == "/config" and method == "GET":
                cfg = config()
                return self.send_json(200, {"server_url": cfg["server_url"], "ready": bool(cfg["server_url"] and cfg["admin_key"])})
            if route == "/overview" and method == "GET":
                if url.query == "cached=1":
                    kept = cached_overview()
                    return self.send_json(200, with_codes(kept, True) if kept else {"users": None})
                return self.send_json(200, with_codes(fresh_overview(), False))
            if route == "/users" and method == "GET":
                users = upstream("GET", "/users")["users"]
                codes = load_codes()
                for u in users:
                    u["code"] = (codes.get(u["id"]) or {}).get("code")
                return self.send_json(200, {"users": users})
            if route == "/users" and method == "POST":
                data = self.body_json()
                res = upstream("POST", "/users", json.dumps(data).encode())
                user = res["user"]
                with _lock:
                    codes = load_codes()
                    codes[user["id"]] = {"code": res["code"], "phone": user["phone"], "memo": user.get("memo"),
                                         "created_at": user["created_at"], "expires_at": user["expires_at"]}
                    save_codes(codes)
                edit_kept_user(user, new=True)
                user["code"] = res["code"]
                return self.send_json(201, {"user": user})
            if route.startswith("/users/") and route.endswith("/download") and method == "GET":
                return self.proxy_download(route, url.query)
            if route.startswith("/users/") and method == "PATCH":
                res = upstream("PATCH", route, json.dumps(self.body_json()).encode())
                user = res["user"]
                with _lock:
                    codes = load_codes()
                    if user["id"] in codes:
                        codes[user["id"]].update({"expires_at": user["expires_at"], "memo": user.get("memo")})
                        save_codes(codes)
                edit_kept_user(user)
                return self.send_json(200, res)
            if route == "/client" and method == "GET":
                return self.send_json(200, upstream("GET", "/client"))
            if route.startswith("/users/") and method == "GET":
                return self.send_json(200, upstream("GET", route))
            return self.send_json(404, {"error": "not found"})
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read()).get("error")
            except ValueError:
                detail = None
            return self.send_json(e.code, {"error": detail or "서버 오류 (%s)" % e.code})
        except (urllib.error.URLError, OSError) as e:
            return self.send_json(502, {"error": "서버에 연결할 수 없습니다: %s" % getattr(e, "reason", e)})
        except RuntimeError as e:
            return self.send_json(500, {"error": str(e)})

    def proxy_download(self, route, query):
        try:
            res = upstream("GET", route + "?" + query, stream=True)
        except urllib.error.HTTPError as e:
            msg = "다운로드할 대화가 없습니다." if e.code == 404 else "다운로드 실패 (%s)" % e.code
            return self.send_json(e.code, {"error": msg})
        with res:
            self.send_response(200)
            for h in ("Content-Type", "Content-Length", "Content-Disposition"):
                if res.headers.get(h):
                    self.send_header(h, res.headers[h])
            self.end_headers()
            while True:
                chunk = res.read(1024 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self.handle_api("GET")
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(body)
        self.send_json(404, {"error": "not found"})

    def do_POST(self):
        self.handle_api("POST")

    def do_PATCH(self):
        self.handle_api("PATCH")


def main():
    cfg = config()
    if not cfg["server_url"] or not cfg["admin_key"]:
        print("admin/config.json 이 비어 있습니다. admin/config.example.json 을 복사해 채워 주세요.", file=sys.stderr)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.daemon_threads = True
    print("session-relay 관리자: http://%s:%d  (서버 %s)" % (HOST, PORT, cfg["server_url"] or "미설정"))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

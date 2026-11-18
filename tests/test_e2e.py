#!/usr/bin/env python3
"""End-to-end test: a real server process, fake Claude Code / Codex folders, the client run with the macOS
python3 (3.9) when it exists. Nothing touches the real ~/.claude, ~/.codex or launchd.

  python3 tests/test_e2e.py
"""
import datetime
import functools
import gzip
import hashlib
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELAY = os.path.join(ROOT, "client", "relay.py")
INSTALL = os.path.join(ROOT, "install.sh")
SERVER = os.path.join(ROOT, "server", "app.py")
ADMIN = os.path.join(ROOT, "admin", "admin.py")
CLIENT_PY = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable
KEY = "test-admin-key"
SID = "11111111-2222-3333-4444-555555555555"
CODEX_SID = "01a1df73-1900-7c23-a90a-0f57f51779ee"
PNG = "iVBORw0KGgo" + "A" * 4000
SECRET = "sk-proj-abc123DEF456ghi789JKL012mno"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def utc(local_text):
    """'2026-11-16 23:50' local time -> ISO UTC with Z, the way the tools write it."""
    moment = datetime.datetime.strptime(local_text, "%Y-%m-%d %H:%M").astimezone()
    return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def line(**kw):
    return json.dumps(kw) + "\n"


def wait_up(url):
    for _ in range(50):
        try:
            urllib.request.urlopen(url + "/health", timeout=1)
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("server did not start")


def call(url, method="GET", body=None, key=KEY, raw=False):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method)
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as res:
        data = res.read()
        return data if raw else json.loads(data)


class E2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="relay-e2e-")
        cls.port = free_port()
        cls.url = "http://127.0.0.1:%d" % cls.port
        env = dict(os.environ, DATA_DIR=os.path.join(cls.tmp, "server"), ADMIN_KEY=KEY, PORT=str(cls.port))
        cls.server = subprocess.Popen([sys.executable, SERVER], env=env, stderr=subprocess.DEVNULL)
        wait_up(cls.url)

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.home = tempfile.mkdtemp(dir=self.tmp)
        self.claude = os.path.join(self.home, "claude-projects")
        self.codex = os.path.join(self.home, "codex")
        proj = os.path.join(self.claude, "-Users-me-proj")
        os.makedirs(os.path.join(proj, SID, "subagents"))
        self.session = os.path.join(proj, SID + ".jsonl")
        with open(self.session, "w") as f:
            f.write(line(type="session-owner", sessionId=SID))  # No timestamp: goes with the first dated line.
            f.write(line(type="user", timestamp=utc("2026-11-16 23:40"), cwd="/Users/me/proj", entrypoint="cli",
                         message={"role": "user", "content": [{"type": "text", "text": "hello"}, {
                             "type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG}}]}))
            f.write(line(type="api-request", timestamp=utc("2026-11-16 23:41"), body="x" * 5000))  # Dropped.
            f.write(line(type="assistant", timestamp=utc("2026-11-16 23:55"),
                         message={"content": "hi, OPENAI_API_KEY=" + SECRET + ", call kim@corp.kr or 010-1234-5678"}))
            f.write(line(type="user", timestamp=utc("2026-11-17 00:10"), message={"content": "after midnight"}))
        with open(os.path.join(proj, SID, "subagents", "agent-1.jsonl"), "w") as f:
            f.write(line(type="user", timestamp=utc("2026-11-16 10:00")))
        with open(os.path.join(proj, "99999999-2222-3333-4444-555555555555.jsonl"), "w") as f:
            f.write(line(type="user", timestamp=utc("2026-11-16 10:00"), entrypoint="sdk-cli"))  # claude -p
        day = os.path.join(self.codex, "sessions", "2026", "11", "16")
        os.makedirs(day)
        with open(os.path.join(day, "rollout-2026-11-16T10-00-00-%s.jsonl" % CODEX_SID), "w") as f:
            f.write(line(timestamp=utc("2026-11-16 10:00"), type="session_meta",
                         payload={"id": CODEX_SID, "cwd": "/Users/me/other", "source": "vscode"}))
            f.write(line(timestamp=utc("2026-11-16 10:01"), type="event_msg", payload={"type": "user_message"}))
        with open(os.path.join(day, "rollout-2026-11-16T11-00-00-01a1df73-0000-7c23-a90a-0f57f51779ee.jsonl"), "w") as f:
            f.write(line(timestamp=utc("2026-11-16 11:00"), type="session_meta", payload={"source": "exec"}))
        imported = "01a1df73-aaaa-7c23-a90a-0f57f51779ee"
        with open(os.path.join(day, "rollout-2026-11-16T12-00-00-%s.jsonl" % imported), "w") as f:
            f.write(line(timestamp=utc("2026-11-16 12:00"), type="session_meta", payload={"source": "vscode"}))
        with open(os.path.join(self.codex, "external_agent_session_imports.json"), "w") as f:
            json.dump({"records": [{"imported_thread_id": imported}]}, f)
        os.makedirs(os.path.join(self.home, ".claude"))
        os.makedirs(os.path.join(self.home, ".codex"))
        self.env = dict(os.environ, HOME=self.home, SESSION_RELAY_LANG="en",
                        SESSION_RELAY_HOME=os.path.join(self.home, ".session-relay"),
                        SESSION_RELAY_CLAUDE_DIR=self.claude, SESSION_RELAY_CODEX_DIR=self.codex,
                        SESSION_RELAY_NO_LAUNCHD="1", SESSION_RELAY_LABEL="io.session-relay.test")

    def relay(self, *args, now=None, server=None):
        env = dict(self.env)
        if now:
            env["SESSION_RELAY_NOW"] = utc(now)
        cmd = [CLIENT_PY, RELAY] + list(args)
        if args[0] == "init":
            cmd += ["--server", server or self.url]
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
        return res.returncode, res.stdout + res.stderr

    def issue(self, phone="010-1234-5678", end="2027-01-01T00:00:00Z"):
        res = call(self.url + "/admin/users", "POST", {"phone": phone, "expires_at": end, "memo": "test"})
        return res["user"]["id"], res["code"]

    def state(self):
        with open(os.path.join(self.env["SESSION_RELAY_HOME"], "state.json")) as f:
            return json.load(f)

    def test_full_flow(self):
        uid, code = self.issue()
        rc, out = self.relay("init", "--code", code.lower().replace("-", " "), "--foreground", now="2026-11-17 09:00")
        self.assertEqual(rc, 0, out)
        self.assertIn("Found 4 session files", out)  # 2 Claude + 2 Codex (imported copy left out)
        days = {d["date"]: d for d in call(self.url + "/admin/users/%s/days" % uid)["days"]}
        self.assertEqual(sorted(days), ["2026-11-16", "2026-11-17"])  # Session cut at midnight.
        self.assertEqual(days["2026-11-16"]["tools"], {"claude": 1, "codex": 1})
        self.assertEqual(days["2026-11-17"]["tools"], {"claude": 1})
        sessions = call(self.url + "/admin/users/%s/days/2026-11-16" % uid)["sessions"]
        claude = [s for s in sessions if s["tool"] == "claude"][0]
        self.assertEqual(claude["lines"], 3)  # owner + user + assistant; api-request dropped
        self.assertEqual(claude["cwd"], "/Users/me/proj")
        self.assertEqual(self.state()["last_result"]["skipped_automated"], 2)

        # Same day: tick does nothing.
        rc, out = self.relay("tick", now="2026-11-17 15:00")
        self.assertEqual((rc, out), (0, ""))
        # Forced sync with no change sends nothing.
        rc, out = self.relay("sync", now="2026-11-17 15:00")
        self.assertIn("Synced: 0 slices", out)

        # The session goes on in the afternoon and the next day.
        with open(self.session, "a") as f:
            f.write(line(type="assistant", timestamp=utc("2026-11-17 14:00"), message={"content": "later"}))
            f.write(line(type="user", timestamp=utc("2026-11-18 08:00"), message={"content": "next day"}))
            f.write('{"type":"user","timestamp":"unfinished')  # Being written right now.
        rc, out = self.relay("tick", now="2026-11-18 09:00")
        self.assertIn("Synced: 2 slices from 1 sessions", out)  # 17th grew, 18th is new; 16th untouched.
        sessions = call(self.url + "/admin/users/%s/days/2026-11-17" % uid)["sessions"]
        self.assertEqual(sessions[0]["lines"], 2)

        zipped = call(self.url + "/admin/users/%s/download?from=2026-11-16&to=2026-11-18" % uid, raw=True)
        names = zipfile.ZipFile(io.BytesIO(zipped)).namelist()
        self.assertIn("01012345678/2026-11-16/claude_%s.jsonl" % SID, names)
        self.assertIn("01012345678/2026-11-18/_index.json", names)
        body = zipfile.ZipFile(io.BytesIO(zipped)).read("01012345678/2026-11-17/claude_%s.jsonl" % SID).decode()
        self.assertIn("after midnight", body)
        day16 = zipfile.ZipFile(io.BytesIO(zipped)).read("01012345678/2026-11-16/claude_%s.jsonl" % SID).decode()
        self.assertIn("[image omitted: image/png", day16)  # Images become a text note before sending.
        self.assertNotIn("A" * 100, day16)
        self.assertIn("OPENAI_API_KEY=[redacted: api key]", day16)  # Secrets are masked before sending.
        self.assertNotIn(SECRET, day16)
        self.assertIn("call [redacted: email]@corp.kr or [redacted: phone]", day16)  # And personal information.
        self.assertNotIn("unfinished", body)

        # The server asks for everything again (it lost the files): the next sync resends all slices.
        call(self.url + "/admin/users/" + uid, "PATCH", {"resend": True})
        rc, out = self.relay("sync", now="2026-11-18 10:00")
        self.assertIn("Synced: 4 slices from 2 sessions", out)
        rc, out = self.relay("sync", now="2026-11-18 10:05")
        self.assertIn("Synced: 0 slices", out)

        # The admin ends the code. The next daily tick hears it from the server and stops for good.
        call(self.url + "/admin/users/" + uid, "PATCH", {"expires_at": "now"})
        rc, out = self.relay("tick", now="2026-11-19 09:00")
        self.assertIn("Stopped (ended)", out)
        self.assertEqual(self.state()["stopped"]["reason"], "expired")
        rc, out = self.relay("tick", now="2026-11-20 09:00")
        self.assertEqual((rc, out), (0, ""))  # No more calls.

    def test_local_expiry_stops_without_calling(self):
        # The server judges the end date by the real clock, so it must still be ahead at install time.
        today = datetime.date.today()
        end = today + datetime.timedelta(days=2)
        uid, code = self.issue(end=end.isoformat() + "T00:00:00Z")
        rc, out = self.relay("init", "--code", code, "--no-job", now=today.isoformat() + " 09:00")
        self.assertEqual(rc, 0, out)
        cfg_path = os.path.join(self.env["SESSION_RELAY_HOME"], "config.json")
        with open(cfg_path) as f:
            cfg = json.load(f)
        cfg["server"] = "http://127.0.0.1:9"  # Nothing listens: a call would fail with a network error.
        with open(cfg_path, "w") as f:
            json.dump(cfg, f)
        rc, out = self.relay("tick", now=(end + datetime.timedelta(days=1)).isoformat() + " 09:00")
        self.assertIn("Stopped (ended)", out)
        self.assertNotIn("reach", out)

    def run_install(self, *args, env=None):
        res = subprocess.run(["sh", INSTALL] + list(args), env=env or self.env, capture_output=True, text=True,
                             timeout=120, cwd=self.home, stdin=subprocess.DEVNULL, start_new_session=True)
        return res.returncode, res.stdout + res.stderr

    def test_install_script_and_uninstall(self):
        uid, code = self.issue()
        rc, out = self.run_install(code, "--server", self.url, "--no-job", "--foreground")
        self.assertEqual(rc, 0, out)
        self.assertIn("Code confirmed", out)
        self.assertIn("Synced: 3 slices", out)
        relay_home = self.env["SESSION_RELAY_HOME"]
        wrapper = os.path.join(relay_home, "relay")
        skills = [os.path.join(self.home, ".claude", "skills", "session-relay", "SKILL.md"),
                  os.path.join(self.home, ".agents", "skills", "session-relay", "SKILL.md")]
        for f in [wrapper, os.path.join(relay_home, "README.md"), os.path.join(relay_home, "app", "relay.py")] + skills:
            self.assertTrue(os.path.exists(f), f)
        res = subprocess.run([wrapper, "status", "--json"], env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout)["slices_sent"], 3)
        res = subprocess.run([wrapper, "uninstall"], env=self.env, capture_output=True, text=True, timeout=60)
        self.assertIn("Removed", res.stdout)
        for f in [relay_home] + skills:
            self.assertFalse(os.path.exists(f), f)

    def test_auto_update(self):
        uid, code = self.issue()
        rc, out = self.run_install(code, "--server", self.url, "--no-job", "--foreground")
        self.assertEqual(rc, 0, out)
        relay_home = self.env["SESSION_RELAY_HOME"]
        wrapper = os.path.join(relay_home, "relay")
        # A release the way GitHub would serve it: <base>/<commit>/<path>.
        root = os.path.join(self.home, "release")

        def make_release(ref, version):
            files = {}
            for rel in ("client/relay.py", "client/sources.py", "client/media.py", "client/redact.py",
                        "client/defaults.json", "skill/SKILL.md"):
                with open(os.path.join(ROOT, rel), "rb") as f:
                    data = f.read()
                if rel == "client/relay.py":
                    data = re.sub(rb'VERSION = "[0-9.]+"', b'VERSION = "%s"' % version.encode(), data, count=1)
                dest = os.path.join(root, ref, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(data)
                files[rel] = hashlib.sha256(data).hexdigest()
            return files

        ref, ref2 = "ab" * 20, "ef" * 20
        files, files2 = make_release(ref, "9.9.9"), make_release(ref2, "9.9.10")
        # GitHub's compare API, answered the same way: the releases are on main; another commit only on a fork.
        fork_ref = "cd" * 20
        os.makedirs(os.path.join(root, "compare"))
        for r, status in ((ref, "ahead"), (ref2, "identical"), (fork_ref, "diverged")):
            with open(os.path.join(root, "compare", r + "...main"), "w") as f:
                json.dump({"status": status}, f)
        handler = functools.partial(SimpleHTTPRequestHandler, directory=root)
        handler.log_message = lambda *a: None
        static = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=static.serve_forever, daemon=True).start()
        self.addCleanup(static.shutdown)
        env = dict(self.env, SESSION_RELAY_UPDATE_BASE="http://127.0.0.1:%d/" % static.server_address[1],
                   SESSION_RELAY_UPDATE_API="http://127.0.0.1:%d/compare/" % static.server_address[1])

        def run(*args, now):
            res = subprocess.run([wrapper] + list(args), env=dict(env, SESSION_RELAY_NOW=utc(now)),
                                 capture_output=True, text=True, timeout=120)
            return res.stdout + res.stderr

        def installed_version():
            return subprocess.run([wrapper, "version"], env=env, capture_output=True, text=True).stdout.strip()

        old = installed_version()
        # A commit that is not on main (pushed to a fork) is refused even with matching hashes.
        call(self.url + "/admin/client", "PUT", {"version": "9.9.9", "ref": fork_ref, "files": files})
        out = run("sync", now="2026-11-17 22:00")
        self.assertIn("Could not update to 9.9.9", out)
        self.assertIn("is not on main (diverged)", out)
        self.assertIn("Synced", out)
        self.assertEqual(installed_version(), old)

        # A file that does not match the server's hash: no update, the sync still runs on the old version.
        bad = dict(files, **{"client/media.py": "0" * 64})
        call(self.url + "/admin/client", "PUT", {"version": "9.9.9", "ref": ref, "files": bad})
        out = run("sync", now="2026-11-18 09:00")
        self.assertIn("Could not update to 9.9.9", out)
        self.assertIn("Synced", out)
        self.assertEqual(installed_version(), old)
        self.assertFalse(os.path.exists(os.path.join(relay_home, "app.new")))

        # The real release: check the code, update, then sync with the new code and record it.
        call(self.url + "/admin/client", "PUT", {"version": "9.9.9", "ref": ref, "files": files})
        out = run("sync", now="2026-11-19 09:00")
        self.assertIn("Updated the client from %s to 9.9.9" % old, out)
        self.assertIn("Synced", out)
        self.assertEqual(installed_version(), "9.9.9")
        self.assertTrue(os.path.exists(os.path.join(relay_home, "app.prev", "relay.py")))
        users = {u["id"]: u for u in call(self.url + "/admin/users")["users"]}
        self.assertEqual(users[uid]["client_version"], "9.9.9")
        with open(os.path.join(relay_home, "state.json")) as f:
            self.assertEqual(json.load(f)["update"]["to"], "9.9.9")
        # Up to date now: no second update.
        out = run("sync", now="2026-11-19 10:00")
        self.assertNotIn("Updated", out)
        out = run("update", now="2026-11-19 10:05")
        self.assertIn("Up to date (9.9.9)", out)

        # `relay update`: a release that failed this morning is not retried by a sync the same day, but update
        # installs it at once, without syncing, and the server records the new version.
        call(self.url + "/admin/client", "PUT",
             {"version": "9.9.10", "ref": ref2, "files": dict(files2, **{"client/media.py": "0" * 64})})
        self.assertIn("Could not update to 9.9.10", run("sync", now="2026-11-20 09:00"))
        call(self.url + "/admin/client", "PUT", {"version": "9.9.10", "ref": ref2, "files": files2})
        out = run("sync", now="2026-11-20 09:30")
        self.assertNotIn("Updated", out)
        self.assertEqual(installed_version(), "9.9.9")
        out = run("update", now="2026-11-20 09:40")
        self.assertIn("Updated the client from 9.9.9 to 9.9.10", out)
        self.assertIn("Up to date (9.9.10)", out)
        self.assertNotIn("Synced", out)
        self.assertEqual(installed_version(), "9.9.10")
        users = {u["id"]: u for u in call(self.url + "/admin/users")["users"]}
        self.assertEqual(users[uid]["client_version"], "9.9.10")

    def test_install_needs_code_without_terminal(self):
        rc, out = self.run_install("--server", self.url)
        self.assertEqual(rc, 2, out)
        self.assertIn("A code is required", out)
        self.assertFalse(os.path.exists(self.env["SESSION_RELAY_HOME"]))

    def test_korean_messages(self):
        env = dict(self.env, SESSION_RELAY_LANG="ko")
        rc, out = self.run_install("--code", "SR-AAAA-BBBB-CCCC-DDDD", "--server", self.url, env=env)
        self.assertEqual(rc, 2, out)
        self.assertIn("접속 코드가 맞지 않습니다", out)

    def test_bad_code(self):
        rc, out = self.relay("init", "--code", "SR-AAAA-BBBB-CCCC-DDDD")
        self.assertEqual(rc, 2)
        self.assertIn("not valid", out)

    def test_ended_code(self):
        uid, code = self.issue(end="2020-01-01T00:00:00Z")
        rc, out = self.relay("init", "--code", code)
        self.assertEqual(rc, 2)
        self.assertIn("already ended", out)

    def test_index_overview_and_restart(self):
        uid, code = self.issue(phone="010-5555-0000")
        rc, out = self.relay("init", "--code", code, "--no-job", "--foreground", now="2026-11-17 09:00")
        self.assertEqual(rc, 0, out)
        req = urllib.request.Request(self.url + "/admin/overview", headers={
            "Authorization": "Bearer " + KEY, "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=10) as res:
            self.assertEqual(res.headers["Content-Encoding"], "gzip")
            tag = res.headers["ETag"]
            data = json.loads(gzip.decompress(res.read()))
        user = [u for u in data["users"] if u["id"] == uid][0]
        self.assertEqual([d["date"] for d in user["days"]], ["2026-11-17", "2026-11-16"])
        self.assertEqual(user["days"][1]["tools"], {"claude": 1, "codex": 1})
        self.assertEqual((user["days_count"], user["sessions_total"]), (2, 3))
        self.assertEqual(data["rev"], tag)

        def conditional(etag):
            r = urllib.request.Request(self.url + "/admin/overview", headers={
                "Authorization": "Bearer " + KEY, "If-None-Match": etag})
            try:
                with urllib.request.urlopen(r, timeout=10) as res:
                    return res.status
            except urllib.error.HTTPError as e:
                return e.code

        self.assertEqual(conditional(tag), 304)
        call(self.url + "/admin/users/" + uid, "PATCH", {"memo": "changed"})
        self.assertEqual(conditional(tag), 200)  # Any write changes the ETag.

        sessions = call(self.url + "/admin/users/%s/days/2026-11-17" % uid)["sessions"]
        self.assertEqual(sessions[0]["dates"], ["2026-11-16", "2026-11-17"])

        # The index is derived: a second server on the same folder, with the index deleted, answers the same.
        data_dir = os.path.join(self.tmp, "server")
        copy = os.path.join(self.tmp, "server-copy")
        shutil.copytree(data_dir, copy)
        for name in os.listdir(copy):
            if name.startswith("index.db"):
                os.remove(os.path.join(copy, name))
        port = free_port()
        proc = subprocess.Popen([sys.executable, SERVER], env=dict(
            os.environ, DATA_DIR=copy, ADMIN_KEY=KEY, PORT=str(port)), stderr=subprocess.DEVNULL)
        try:
            other = "http://127.0.0.1:%d" % port
            wait_up(other)
            self.assertEqual(call(other + "/admin/users/%s/days" % uid)["days"], user["days"])
            self.assertEqual(call(other + "/admin/users/%s/days/2026-11-17" % uid)["sessions"], sessions)
            self.assertEqual(call(other + "/v1/me", key=code)["status"], "active")  # Users load from users.json.
        finally:
            proc.terminate()
            proc.wait()

    def test_batch_upload(self):
        uid, code = self.issue(phone="010-7777-0000")
        good = gzip.compress(b'{"type":"user"}\n')
        manifest = {"slices": [
            {"date": "2026-11-10", "tool": "claude", "session_id": "abc", "size": len(good),
             "meta": {"lines": 1, "cwd": "/w", "media_stripped": 1}},
            {"date": "2026-11-10", "tool": "nope", "session_id": "abc", "size": len(good), "meta": {}},
            {"date": "2026-11-11", "tool": "codex", "session_id": "def", "size": 3, "meta": {}}],
            "report": {"reason": "test", "slices": 1, "client_version": "0.7.0"}}
        body = b"SRB1\n" + json.dumps(manifest).encode() + b"\n" + good + good + b"xyz"
        req = urllib.request.Request(self.url + "/v1/batch", data=body, method="POST")
        req.add_header("Authorization", "Bearer " + code)
        with urllib.request.urlopen(req, timeout=10) as res:
            results = json.loads(res.read())["results"]
        self.assertEqual([r["ok"] for r in results], [True, False, False])  # Bad path, not gzip: the rest stays.
        self.assertEqual(call(self.url + "/admin/users/%s/days" % uid)["days"][0]["date"], "2026-11-10")
        user = call(self.url + "/admin/users/" + uid)["user"]
        self.assertEqual((user["last_sync"]["reason"], user["client_version"]), ("test", "0.7.0"))
        req = urllib.request.Request(self.url + "/v1/batch", data=body[:-1], method="POST")  # Sizes do not add up.
        req.add_header("Authorization", "Bearer " + code)
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(e.exception.code, 400)

    def test_admin_requires_key(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            call(self.url + "/admin/users", key="wrong")
        self.assertEqual(e.exception.code, 401)

    def test_admin_web_records_code(self):
        port = free_port()
        data = os.path.join(ROOT, "admin", "data")
        backup = data + ".bak-test" if os.path.exists(data) else None
        if backup:
            os.rename(data, backup)
        env = dict(os.environ, SESSION_RELAY_SERVER=self.url, SESSION_RELAY_ADMIN_KEY=KEY,
                   SESSION_RELAY_ADMIN_PORT=str(port))
        proc = subprocess.Popen([sys.executable, ADMIN], env=env, stdout=subprocess.DEVNULL)
        try:
            base = "http://127.0.0.1:%d" % port
            for _ in range(50):
                try:
                    urllib.request.urlopen(base + "/api/config", timeout=1)
                    break
                except OSError:
                    time.sleep(0.1)
            res = call(base + "/api/users", "POST", {"phone": "010-9999-0000", "expires_at": "2027-01-01T00:00:00Z"})
            code = res["user"]["code"]
            with open(os.path.join(data, "codes.json")) as f:
                self.assertEqual(json.load(f)[res["user"]["id"]]["code"], code)
            listed = call(base + "/api/users")["users"]
            self.assertEqual([u["code"] for u in listed if u["id"] == res["user"]["id"]], [code])
            # The overview: kept after the first fetch, then checked with one conditional request.
            self.assertIsNone(call(base + "/api/overview?cached=1")["users"])
            fresh = call(base + "/api/overview")
            self.assertFalse(fresh["cached"])
            self.assertEqual([u["code"] for u in fresh["users"] if u["id"] == res["user"]["id"]], [code])
            kept = call(base + "/api/overview?cached=1")
            self.assertTrue(kept["cached"])
            self.assertEqual(kept["rev"], fresh["rev"])
            self.assertEqual(call(base + "/api/overview")["rev"], fresh["rev"])  # 304 upstream: same data.
            with open(os.path.join(data, "overview.json")) as f:
                self.assertEqual(json.load(f)["etag"], fresh["rev"])
            self.assertEqual(os.stat(os.path.join(data, "overview.json")).st_mode & 0o777, 0o600)
            # A change made here shows in the kept copy at once, and the next check brings the server's answer.
            call(base + "/api/users/" + res["user"]["id"], "PATCH", {"memo": "edited"})
            kept = call(base + "/api/overview?cached=1")
            self.assertEqual([u["memo"] for u in kept["users"] if u["id"] == res["user"]["id"]], ["edited"])
            again = call(base + "/api/overview")
            self.assertNotEqual(again["rev"], fresh["rev"])
            req = urllib.request.Request(base + "/api/users", headers={"Origin": "https://evil.example"})
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(req)
        finally:
            proc.terminate()
            proc.wait()
            shutil.rmtree(data, ignore_errors=True)
            if backup:
                os.rename(backup, data)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""End-to-end test: a real server process, fake Claude Code / Codex folders, the client run with the macOS
python3 (3.9) when it exists. Nothing touches the real ~/.claude, ~/.codex or launchd.

  python3 tests/test_e2e.py
"""
import datetime
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
RELAY = os.path.join(ROOT, "skills", "session-relay", "scripts", "relay.py")
SERVER = os.path.join(ROOT, "server", "app.py")
ADMIN = os.path.join(ROOT, "admin", "admin.py")
CLIENT_PY = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable
KEY = "test-admin-key"
SID = "11111111-2222-3333-4444-555555555555"
CODEX_SID = "01a1df73-1900-7c23-a90a-0f57f51779ee"


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
                         message={"role": "user", "content": "hello"}))
            f.write(line(type="api-request", timestamp=utc("2026-11-16 23:41"), body="x" * 5000))  # Dropped.
            f.write(line(type="assistant", timestamp=utc("2026-11-16 23:55"), message={"content": "hi"}))
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
        self.env = dict(os.environ, SESSION_RELAY_HOME=os.path.join(self.home, "relay"),
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
        self.assertNotIn("unfinished", body)

        # The admin ends the code. The next daily tick hears it from the server and stops for good.
        call(self.url + "/admin/users/" + uid, "PATCH", {"expires_at": "now"})
        rc, out = self.relay("tick", now="2026-11-19 09:00")
        self.assertIn("Stopped (expired)", out)
        self.assertEqual(self.state()["stopped"]["reason"], "expired")
        rc, out = self.relay("tick", now="2026-11-20 09:00")
        self.assertEqual((rc, out), (0, ""))  # No more calls.

    def test_local_expiry_stops_without_calling(self):
        uid, code = self.issue(end="2026-11-18T00:00:00Z")
        rc, out = self.relay("init", "--code", code, "--no-job", now="2026-11-17 09:00")
        self.assertEqual(rc, 0, out)
        cfg_path = os.path.join(self.env["SESSION_RELAY_HOME"], "config.json")
        with open(cfg_path) as f:
            cfg = json.load(f)
        cfg["server"] = "http://127.0.0.1:9"  # Nothing listens: a call would fail with a network error.
        with open(cfg_path, "w") as f:
            json.dump(cfg, f)
        rc, out = self.relay("tick", now="2026-11-19 09:00")
        self.assertIn("Stopped (expired)", out)
        self.assertNotIn("reach", out)

    def test_bad_code(self):
        rc, out = self.relay("init", "--code", "SR-AAAA-BBBB-CCCC-DDDD")
        self.assertEqual(rc, 2)
        self.assertIn("not valid", out)

    def test_ended_code(self):
        uid, code = self.issue(end="2020-01-01T00:00:00Z")
        rc, out = self.relay("init", "--code", code)
        self.assertEqual(rc, 2)
        self.assertIn("already ended", out)

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

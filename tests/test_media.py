#!/usr/bin/env python3
"""Images in session lines become short text notes, in the client and on the server.

  python3 tests/test_media.py
"""
import base64
import gzip
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "client"))
import media  # noqa: E402

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + os.urandom(3000)).decode()
JPG = base64.b64encode(b"\xff\xd8\xff\xe0" + os.urandom(3000)).decode()
PDF = base64.b64encode(b"%PDF-1.7\n" + os.urandom(3000)).decode()


def line(obj):
    return (json.dumps(obj) + "\n").encode()


class Shapes(unittest.TestCase):
    def strip(self, obj):
        out, n = media.strip_line(line(obj))
        return json.loads(out), n, out

    def test_claude_message_image(self):
        obj = {"type": "user", "message": {"content": [
            {"type": "text", "text": "look"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG}}]}}
        new, n, raw = self.strip(obj)
        self.assertEqual(n, 1)
        self.assertEqual(new["message"]["content"][0], {"type": "text", "text": "look"})
        self.assertEqual(new["message"]["content"][1]["type"], "text")
        self.assertRegex(new["message"]["content"][1]["text"], r"^\[image omitted: image/png, \d+ KB\]$")
        self.assertNotIn(PNG[:40].encode(), raw)

    def test_claude_tool_result_and_tool_use_result(self):
        obj = {"type": "user",
               "message": {"content": [{"type": "tool_result", "content": [
                   {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": JPG}}]}]},
               "toolUseResult": {"type": "image", "file": {"base64": PNG, "type": "image/png"}}}
        new, n, raw = self.strip(obj)
        self.assertEqual(n, 2)
        self.assertIn("image/jpeg", new["message"]["content"][0]["content"][0]["text"])
        self.assertRegex(new["toolUseResult"]["file"]["base64"], r"^\[image omitted: image/png")
        self.assertEqual(new["toolUseResult"]["file"]["type"], "image/png")

    def test_codex_input_image_and_pdf(self):
        obj = {"type": "response_item", "payload": {"content": [
            {"type": "input_image", "image_url": "data:image/png;base64," + PNG},
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": PDF}}]}}
        new, n, _ = self.strip(obj)
        self.assertEqual(n, 2)
        self.assertEqual(new["payload"]["content"][0]["type"], "input_text")
        self.assertIn("[image omitted: image/png", new["payload"]["content"][0]["text"])
        self.assertIn("[file omitted: application/pdf", new["payload"]["content"][1]["text"])

    def test_text_is_left_alone(self):
        for obj in ({"type": "user", "message": {"content": "the word base64 and /9j/ in plain text"}},
                    {"type": "assistant", "message": {"content": [{"type": "text", "text": "x" * 5000}]}}):
            raw = line(obj)
            self.assertEqual(media.strip_line(raw), (raw, 0))

    def test_deterministic(self):
        obj = {"a": {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG}}, "한": "글"}
        self.assertEqual(media.strip_line(line(obj)), media.strip_line(line(obj)))

    def test_client_and_server_copies_match(self):
        with open(os.path.join(ROOT, "client", "media.py"), "rb") as a, \
                open(os.path.join(ROOT, "server", "media.py"), "rb") as b:
            self.assertEqual(a.read(), b.read(), "server/media.py must be a copy of client/media.py")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Server(unittest.TestCase):
    """Old clients send images; the server strips them on upload and cleans files stored before."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="relay-media-")
        self.image_line = line({"type": "user", "timestamp": "2026-11-06T01:00:00Z", "message": {"content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG}}]}})
        # A file stored by the earlier server, before images were stripped.
        old = os.path.join(self.tmp, "users", "u_0123456789", "2026-11-06")
        os.makedirs(old)
        with open(os.path.join(old, "claude_old.jsonl.gz"), "wb") as f:
            f.write(gzip.compress(self.image_line))
        with open(os.path.join(old, "claude_old.meta.json"), "w") as f:
            json.dump({"tool": "claude", "session_id": "old", "lines": 1}, f)
        self.old = old
        self.port = free_port()
        env = dict(os.environ, DATA_DIR=self.tmp, ADMIN_KEY="k", PORT=str(self.port))
        self.proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "server", "app.py")], env=env,
                                     stderr=subprocess.DEVNULL)
        self.url = "http://127.0.0.1:%d" % self.port
        for _ in range(100):
            try:
                urllib.request.urlopen(self.url + "/health", timeout=1)
                break
            except OSError:
                time.sleep(0.1)

    def tearDown(self):
        self.proc.terminate()
        self.proc.wait()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, route, method="GET", body=None, key="k", headers=None):
        req = urllib.request.Request(self.url + route, data=body, method=method)
        req.add_header("Authorization", "Bearer " + key)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read() or b"{}")

    def read(self, path):
        with gzip.open(path) as f:
            return f.read()

    def test_stored_files_are_cleaned_at_start(self):
        path = os.path.join(self.old, "claude_old.jsonl.gz")
        for _ in range(50):
            with open(os.path.join(self.old, "claude_old.meta.json")) as f:
                meta = json.load(f)
            if meta.get("media_stripped"):
                break
            time.sleep(0.1)
        self.assertEqual(meta["media_removed"], 1)
        data = self.read(path)
        self.assertIn(b"[image omitted: image/png", data)
        self.assertNotIn(PNG[:40].encode(), data)

    def test_old_client_upload_is_stripped(self):
        code = self.call("/admin/users", "POST", json.dumps({"phone": "010-1111-2222",
                                                              "expires_at": "2099-01-01T00:00:00Z"}).encode())["code"]
        uid = self.call("/v1/me", key=code)["user_id"]
        self.call("/v1/sessions/2026-11-06/claude/abc", "PUT", gzip.compress(self.image_line), key=code,
                  headers={"Content-Encoding": "gzip", "X-Relay-Meta": json.dumps({"lines": 1})})
        folder = os.path.join(self.tmp, "users", uid, "2026-11-06")
        data = self.read(os.path.join(folder, "claude_abc.jsonl.gz"))
        self.assertIn(b"[image omitted", data)
        with open(os.path.join(folder, "claude_abc.meta.json")) as f:
            meta = json.load(f)
        self.assertEqual((meta["media_removed"], meta["media_stripped"]), (1, media.VERSION))
        # A new client already stripped: stored exactly as sent.
        body = gzip.compress(b'{"type":"user","note":"[image omitted: image/png, 3 KB]"}\n')
        self.call("/v1/sessions/2026-11-06/claude/new", "PUT", body, key=code,
                  headers={"Content-Encoding": "gzip", "X-Relay-Meta": json.dumps({"media_stripped": media.VERSION})})
        with open(os.path.join(folder, "claude_new.jsonl.gz"), "rb") as f:
            self.assertEqual(f.read(), body)


if __name__ == "__main__":
    unittest.main(verbosity=2)

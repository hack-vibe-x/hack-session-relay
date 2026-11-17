#!/usr/bin/env python3
"""Secrets and personal information in session lines are masked on this computer before they are sent.

  python3 tests/test_redact.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "client"))
import redact  # noqa: E402
import sources  # noqa: E402

KEY_BODY = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7" * 3
ANTHROPIC = "sk-ant-api03-AbCdEf1234567890AbCdEf1234567890"
GITHUB = "ghp_aBcDeF1234567890aBcDeF1234567890abcd"


def mask(text):
    count = [0]
    return redact.redact_text(text, count), count[0]


class Text(unittest.TestCase):
    def assertMasked(self, text, expected, n=1):
        out, count = mask(text)
        self.assertEqual(out, expected)
        self.assertEqual(count, n)

    def test_known_key_formats(self):
        self.assertMasked("export OPENAI_API_KEY=sk-proj-abc123DEF456ghi789JKL012mno",
                          "export OPENAI_API_KEY=[redacted: api key]")
        self.assertMasked("token " + GITHUB + " here", "token [redacted: github token] here")
        self.assertMasked("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE", "AWS_ACCESS_KEY_ID=[redacted: aws key]")
        self.assertMasked("key AIzaSyA1234567890abcdefghijklmnopqrstuv", "key [redacted: google key]")
        self.assertMasked("xoxb-1234567890-abcdefghij", "[redacted: slack token]")
        self.assertMasked("sh -s SR-7K3M-Q9PX-2HVT-W8RN", "sh -s [redacted: session-relay code]")

    def test_private_key(self):
        pem = "-----BEGIN PRIVATE KEY-----\n%s\n%s\n-----END PRIVATE KEY-----" % (KEY_BODY, KEY_BODY)
        self.assertMasked("before\n" + pem + "\nafter.", "before\n[redacted: private key]\nafter.")
        cut = "-----BEGIN RSA PRIVATE KEY-----\n%s\n(output truncated)" % KEY_BODY
        self.assertMasked(cut, "[redacted: private key](output truncated)")

    def test_headers_urls_and_assignments(self):
        self.assertMasked("Authorization: Bearer abcdef0123456789abcdef", "Authorization: Bearer [redacted: credential]")
        self.assertMasked("DATABASE_URL=postgres://admin:S3cretPass@db.example.com:5432/app",
                          "DATABASE_URL=postgres://admin:[redacted: password]@db.example.com:5432/app")
        self.assertMasked('{"apiKey": "Zx81kfj20Lk", "password": "hunter22!"}',
                          '{"apiKey": "[redacted: secret]", "password": "[redacted: secret]"}', 2)
        self.assertMasked("aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                          "aws_secret_access_key = [redacted: secret]")
        self.assertMasked("SOLAPI_API_SECRET=abc123def456ghi", "SOLAPI_API_SECRET=[redacted: secret]")

    def test_json_inside_a_string(self):
        # Codex keeps some tool output as a JSON string, so a line break shows up as a backslash and an n.
        text = '{\\"output\\":\\"a\\n%s\\n\\"}' % ANTHROPIC
        self.assertMasked(text, '{\\"output\\":\\"a\\n[redacted: api key]\\n\\"}')

    def test_code_and_prose_are_left_alone(self):
        for text in ("token = get_token()",
                     "max_tokens=4096 and input_tokens: 12345678",
                     "accessToken: response.data.token,",
                     'password = os.environ["DB_PASSWORD"]',
                     "the disk-usage-monitoring-service-runner-1 is fine",
                     "TOKEN_URL=https://oauth2.googleapis.com/token",
                     'fetch(url, {credentials: "same-origin"})',
                     'if (pem.startsWith("-----BEGIN PRIVATE KEY-----")) {}',
                     "a basic understanding of bearer bonds",
                     "token: string; password: string;"):
            self.assertEqual(mask(text), (text, 0), text)


def pii(text):
    count = [0]
    return redact.redact_pii_text(text, count), count[0]


class PersonalInformation(unittest.TestCase):
    def assertMasked(self, text, expected, n=1):
        self.assertEqual(pii(text), (expected, n))

    def test_email_keeps_the_domain(self):
        self.assertMasked("연락처 hong.gildong@gmail.com, kim@imaginefutures.co",
                          "연락처 [redacted: email]@gmail.com, [redacted: email]@imaginefutures.co", 2)

    def test_korean_phones(self):
        self.assertMasked("010-1234-5678 / 01098765432 / 010 1234 5678 / +82 10-1234-5678 / 02-123-4567 / 031-1234-5678",
                          " / ".join(["[redacted: phone]"] * 6), 6)

    def test_international_phones(self):
        self.assertMasked("US +1 415 555 1234, E164 +14155551234", "US [redacted: phone], E164 [redacted: phone]", 2)

    def test_resident_and_card_numbers(self):
        self.assertMasked("주민번호 900101-1234567", "주민번호 [redacted: resident number]")
        self.assertMasked("card 4111 1111 1111 1111 or 4111-1111-1111-1111",
                          "card [redacted: card number] or [redacted: card number]", 2)

    def test_look_alikes_are_left_alone(self):
        for text in ("Co-Authored-By: Claude <noreply@anthropic.com>", "git@github.com:org/repo.git",
                     "icon@2x.png", "test@example.com", "react@18.3.1 and @types/node",
                     "12345+bot@users.noreply.github.com",
                     "2026-11-17T12:00:00+09:00 and 2026-11-17 10:00", "timestamp 1731830400000 ms",
                     "uuid 12345678-1234-1234-4111-111111111111", "version 1.2.3+20240101 build",
                     "order 2024-0101-1234", "phone hint 010-****-5678", "sha 0101234567890abcdef",
                     "Luhn fails 4111 1111 1111 1112", "mixed 4111-1111 1111-1111", "cost 0.4111111111111111",
                     "id_01012345678"):
            self.assertEqual(pii(text), (text, 0), text)


class Lines(unittest.TestCase):
    def test_line_with_secrets(self):
        obj = {"type": "user", "message": {"content": "my key is " + ANTHROPIC},
               "toolUseResult": {"Password": "abc"}, "usage": {"input_tokens": 5}}
        out, n = redact.redact_line((json.dumps(obj) + "\n").encode())
        self.assertEqual(n, 2)
        new = json.loads(out)
        self.assertEqual(new["message"]["content"], "my key is [redacted: api key]")
        self.assertEqual(new["toolUseResult"]["Password"], "[redacted: secret]")
        self.assertEqual(new["usage"], {"input_tokens": 5})
        self.assertNotIn(ANTHROPIC.encode(), out)

    def test_clean_line_is_returned_as_is(self):
        raw = b'{"type": "assistant", "message": {"content": "hi"}, "usage": {"output_tokens": 3}}\n'
        self.assertIs(redact.redact_line(raw)[0], raw)

    def test_damaged_line(self):
        raw = b"not json " + GITHUB.encode() + b" \xff\n"
        self.assertEqual(redact.redact_line(raw), (b"not json [redacted: github token] \xff\n", 1))

    def test_personal_information_in_a_line(self):
        obj = {"type": "user", "message": {"content": "a\nkim@corp.kr\n010-9876-5432"},
               "uuid": "12345678-1234-1234-4111-111111111111"}
        out, n = redact.redact_line((json.dumps(obj, ensure_ascii=False) + "\n").encode())
        self.assertEqual(n, 2)
        new = json.loads(out)
        self.assertEqual(new["message"]["content"], "a\n[redacted: email]@corp.kr\n[redacted: phone]")
        self.assertEqual(new["uuid"], obj["uuid"])

    def test_json_inside_a_string_stays_valid(self):
        inner = json.dumps({"o": "line\nlee@corp.kr\n+82 10-1111-2222"})
        out, n = redact.redact_line((json.dumps({"out": inner}) + "\n").encode())
        self.assertEqual(n, 2)
        self.assertEqual(json.loads(json.loads(out)["out"]), {"o": "line\n[redacted: email]@corp.kr\n[redacted: phone]"})

    def test_number_outside_a_string(self):
        # A JSON number that looks like a card number is not touched; the same digits in a string are.
        raw = b'{"id": 4111111111111111, "note": "card 4111 1111 1111 1111"}\n'
        out, n = redact.redact_line(raw)
        self.assertEqual(n, 1)
        self.assertEqual(json.loads(out), {"id": 4111111111111111, "note": "card [redacted: card number]"})

    def test_deterministic(self):
        raw = (json.dumps({"a": "OPENAI_API_KEY=" + ANTHROPIC, "b": [GITHUB]}) + "\n").encode()
        self.assertEqual(redact.redact_line(raw), redact.redact_line(raw))


class Sessions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_read_slices_masks_and_counts(self):
        path = os.path.join(self.tmp, "s.jsonl")
        with open(path, "w") as f:
            f.write(json.dumps({"type": "summary", "note": "key " + GITHUB}) + "\n")  # No timestamp.
            f.write(json.dumps({"type": "user", "timestamp": "2026-11-16T10:00:00Z",
                                "message": {"content": "use " + ANTHROPIC}}) + "\n")
            f.write(json.dumps({"type": "assistant", "timestamp": "2026-11-16T10:01:00Z",
                                "message": {"content": "ok"}}) + "\n")
        parsed = sources.read_slices({"tool": "claude", "session_id": "s", "path": path})
        [piece] = parsed["days"].values()
        self.assertEqual(piece["secrets"], 2)
        self.assertEqual(piece["lines"], 3)
        self.assertNotIn(ANTHROPIC.encode(), piece["data"])
        self.assertNotIn(GITHUB.encode(), piece["data"])
        self.assertIn(b'"content":"ok"', piece["data"].replace(b" ", b""))


if __name__ == "__main__":
    unittest.main()

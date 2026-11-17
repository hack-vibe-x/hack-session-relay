"""Masks secrets (API keys, tokens, passwords, private keys) in session lines before they leave this computer.

Standard library only, Python 3.9+. Every string in a line is checked against the patterns below, and a match is
replaced with a short note:

    [redacted: github token]

Session records hold more than the conversation: the output of every command and every file the agent read, so a
`.env` file or `cat ~/.aws/credentials` ends up in them too. The patterns find known key formats, credentials in
URLs, Authorization headers and values assigned to names such as API_KEY, PASSWORD or client_secret. A secret in a
format none of them knows is not found.

The result is deterministic, so the same line always gives the same bytes (the client's hashes depend on it).
Raise VERSION when the patterns change: the client then reads every session again and sends the slices that
changed, which overwrites the copies on the server.

Speed: sessions run to gigabytes, and Python's regular expressions are slow when a pattern starts with an
alternation, a lookbehind or IGNORECASE. So every pattern here starts with a fixed string, runs only when that
string is in the text (a plain substring test), and name patterns run on an ASCII-lowercased copy.
"""
import json
import re

VERSION = 1

LEAD = re.compile(r"[A-Za-z0-9_-]")

# (kind, fixed start, rest of the pattern). Each one runs only when its fixed start is in the text.
TOKEN_PATTERNS = [
    # Only with a key body after the header (code that merely mentions the header is left alone). Up to the END
    # line, or where the base64 stops when the key was cut off.
    ("private key", "-----BEGIN ", r"[A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----(?:\s|\\[nr])*"
                                   r"(?:[A-Za-z-]+: [^\n\\]*(?:\s|\\[nr])*)*[A-Za-z0-9+/=]{40,}"
                                   r"(?:[A-Za-z0-9+/=\r\n]|\\[nr])*?"
                                   r"(?:-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|(?![A-Za-z0-9+/=\r\n]|\\[nr]))"),
    ("session-relay code", "SR-", r"[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}(?![A-Za-z0-9])"),
    ("api key", "sk-", r"[A-Za-z0-9_-]{20,}"),
    ("stripe key", "sk_", r"(?:live|test)_[A-Za-z0-9]{16,}"),
    ("stripe key", "rk_", r"(?:live|test)_[A-Za-z0-9]{16,}"),
    ("github token", "gh", r"[pousr]_[A-Za-z0-9]{30,}"),
    ("github token", "github_pat_", r"[A-Za-z0-9_]{30,}"),
    ("gitlab token", "glpat-", r"[A-Za-z0-9_-]{20,}"),
    ("aws key", "AKIA", r"[0-9A-Z]{16}(?![0-9A-Za-z])"),
    ("aws key", "ASIA", r"[0-9A-Z]{16}(?![0-9A-Za-z])"),
    ("google key", "AIza", r"[0-9A-Za-z_-]{35}"),
    ("google token", "ya29.", r"[0-9A-Za-z_-]{20,}"),
    ("google secret", "GOCSPX-", r"[0-9A-Za-z_-]{20,}"),
    ("slack token", "xox", r"[abposr]-[0-9A-Za-z-]{10,}"),
    ("slack webhook", "https://hooks.slack.com/services/", r"[A-Za-z0-9/_-]+"),
    ("huggingface token", "hf_", r"[A-Za-z0-9]{30,}"),
    ("npm token", "npm_", r"[A-Za-z0-9]{36}"),
    ("sendgrid key", "SG.", r"[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"),
    ("jwt", "eyJ", r"[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
]
TOKENS = [(kind, start, re.compile(re.escape(start) + rest)) for kind, start, rest in TOKEN_PATTERNS]

# Names whose value is a secret: OPENAI_API_KEY, db_password, clientSecret, auth_token (not max_tokens).
KEY_PREFIXES = ("api", "access", "private", "encryption", "signing", "master", "license", "client", "auth")
NAME_PATTERNS = [("secret", "secret"), ("token", "token(?!s)"), ("passw", "passw(?:or)?d"),
                 ("passphrase", "passphrase"), ("credential", "credentials?")] + [
                    (p, p + "[_-]?key") for p in KEY_PREFIXES]
# On ASCII-lowercased text. The match starts at the word itself, so OPENAI_ before API_KEY stays as it is.
ASSIGN_TAIL = (r"[a-z0-9_.-]*\\?[\"']?\s*(?::=|=>|=|:)\s*)"
               r"(?:(?P<q>\\?[\"'])(?P<quoted>[^\"'\s\\]{8,})(?P=q)"
               r"|(?P<bare>[a-z0-9_+/=.~!@#%^*-]{8,})(?=$|[\s,;'\"})\]&\\]))")
ASSIGNS = [(start, re.compile("(?P<head>" + word + ASSIGN_TAIL)) for start, word in NAME_PATTERNS]
NAME = re.compile(r"^[a-z0-9_.-]*(?:%s)[a-z0-9_.-]*$" % "|".join(word for _start, word in NAME_PATTERNS))

AUTH_HEADER = re.compile(r"(?i)\b(bearer|basic)(\s+)([A-Za-z0-9._~+/-]{16,}=*)")
URL_PASSWORD = re.compile(r"(?i)\b([a-z][a-z0-9+.-]{1,20}://[^\s:/@\"'<>]+):([^\s@/\"'<>]+)@")
# Values that sit next to secret-looking names but are not secrets (fetch's credentials option and the like).
NOT_SECRET = {"same-origin", "include", "omit", "password", "undefined", "required", "optional", "changeme"}
LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")  # Keeps every position.

# The gate before a line is parsed again. The same fixed strings, which hold in JSON-escaped text too.
B_TOKEN_STARTS = tuple(sorted({start.encode() for _kind, start, _rest in TOKEN_PATTERNS} - {b"gh"})) + (
    b"ghp_", b"gho_", b"ghu_", b"ghs_", b"ghr_")
B_NAME_STARTS = (b"secret", b"passw", b"passphrase", b"credential", b"bearer", b"basic")


def note(kind):
    return "[redacted: %s]" % kind


def _has_digit(text):
    return any(ch.isdigit() for ch in text)


def _glued(text, at):
    """True when the match at `at` continues a word ("task-..."): then it is not a key. An escaped \\n, \\r or
    \\t before it (JSON inside a string) counts as a line break, not as the letter n."""
    if not at or not LEAD.match(text, at - 1):
        return False
    return not (at >= 2 and text[at - 2] == "\\" and text[at - 1] in "nrt")


def maybe_line(raw):
    """False when a JSONL line (bytes) certainly holds nothing to mask."""
    if any(h in raw for h in B_TOKEN_STARTS):
        return True
    low = raw.lower()
    if any(h in low for h in B_NAME_STARTS) or (b"://" in raw and b"@" in raw):
        return True
    if b"key" in low and any(p.encode() in low for p in KEY_PREFIXES):
        return True
    return low.count(b"token") > low.count(b"tokens")  # auth_token yes; input_tokens (every Claude line) no.


def _tokens(text, count):
    for kind, start, pattern in TOKENS:
        if start not in text:
            continue

        def sub(m, kind=kind, text=text):
            if kind not in ("private key", "slack webhook") and _glued(text, m.start()):
                return m.group(0)
            if kind == "api key" and not _has_digit(m.group(0)):
                return m.group(0)  # sk- inside ordinary words.
            count[0] += 1
            return note(kind)
        text = pattern.sub(sub, text)
    return text


def _assigns(text, low, count):
    for start, pattern in ASSIGNS:
        if start not in low:
            continue
        out, last = [], 0
        for m in pattern.finditer(low):
            group = "quoted" if m.group("quoted") else "bare"
            a, b = m.span(group)
            value = text[a:b]
            if value.isdigit() or value.lower() in NOT_SECRET:
                continue
            if group == "bare" and not _has_digit(value):
                continue  # A bare value without a digit is far more often code (response.data.token).
            count[0] += 1
            out.append(text[last:a])
            out.append(note("secret"))
            last = b
        if out:
            out.append(text[last:])
            text = "".join(out)
            low = text.translate(LOWER)
    return text


def redact_text(text, count):
    """Masks the secrets in one string; count[0] goes up by the number masked."""
    before = count[0]
    text = _tokens(text, count)
    low = text.translate(LOWER)
    if "bearer" in low or "basic" in low:
        def auth(m):
            count[0] += 1
            return m.group(1) + m.group(2) + note("credential")
        text = AUTH_HEADER.sub(auth, text)
    if "://" in text and "@" in text:
        def url(m):
            count[0] += 1
            return m.group(1) + ":" + note("password") + "@"
        text = URL_PASSWORD.sub(url, text)
    if count[0] != before:
        low = text.translate(LOWER)
    return _assigns(text, low, count)


def _walk(value, count, key=None):
    if isinstance(value, dict):
        return {k: _walk(v, count, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(v, count) for v in value]
    if isinstance(value, str):
        if (key and value and not value.startswith("[redacted") and value.lower() not in NOT_SECRET
                and NAME.match(key.translate(LOWER))):
            count[0] += 1
            return note("secret")
        if len(value) >= 8:
            return redact_text(value, count)
    return value


def redact_obj(obj):
    """(new object, number of secrets masked)."""
    count = [0]
    out = _walk(obj, count)
    return out, count[0]


def redact_line(raw, obj=None):
    """One JSONL line (bytes, ending in a newline) -> (bytes, number masked). Unchanged lines come back as is.
    obj is the line already parsed, when the caller has it."""
    if not maybe_line(raw):
        return raw, 0
    if obj is None:
        try:
            obj = json.loads(raw)
        except ValueError:
            # Not JSON (a damaged line): mask the text as it is. surrogateescape keeps any odd bytes unchanged.
            count = [0]
            text = redact_text(raw.decode("utf-8", "surrogateescape"), count)
            return (text.encode("utf-8", "surrogateescape"), count[0]) if count[0] else (raw, 0)
    new, n = redact_obj(obj)
    if not n:
        return raw, 0
    return (json.dumps(new, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"), n

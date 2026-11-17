"""Masks secrets (API keys, tokens, passwords, private keys) and personal information (email addresses, phone
numbers, resident registration numbers, card numbers) in session lines before they leave this computer.

Standard library only, Python 3.9+. Every string in a line is checked against the patterns below, and a match is
replaced with a short note:

    [redacted: github token]

Session records hold more than the conversation: the output of every command and every file the agent read, so a
`.env` file or `cat ~/.aws/credentials` ends up in them too. The patterns find known key formats, credentials in
URLs, Authorization headers and values assigned to names such as API_KEY, PASSWORD or client_secret. A secret in a
format none of them knows is not found.

Personal information: an email address keeps its domain ("[redacted: email]@company.com"); phone numbers are Korean
ones (010-1234-5678, 02-123-4567, +82 10 ...) and international ones written with "+"; resident registration
numbers need the dash (13 digits alone are too often a timestamp); card numbers must pass the Luhn check. Names and
addresses have no fixed form and are not found.

The result is deterministic, so the same line always gives the same bytes (the client's hashes depend on it).
Raise VERSION when the patterns change: the client then reads every session again and sends the slices that
changed, which overwrites the copies on the server.

Speed: sessions run to gigabytes, and Python's regular expressions are slow when a pattern starts with an
alternation, a lookbehind or IGNORECASE. So every pattern here starts with a fixed string, runs only when that
string is in the text (a plain substring test), and name patterns run on an ASCII-lowercased copy.
"""
import json
import re

VERSION = 2  # 2: personal information.

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

# Personal information is searched in the raw line (bytes, still JSON-escaped), not string by string: emails and
# numbers look the same escaped, and walking every string of every line was the slow part. A line that would no
# longer parse after the change (a JSON number that looks like a card number) is done string by string instead.
# An escaped line break (\n) before a match counts as a boundary, not as the letter n.

# Email: the local part is masked, the domain kept. Not for git@github.com, noreply addresses, example domains or
# retina image names like icon@2x.png.
EMAIL = re.compile(rb"(?:(?<=\\[nrtbf])|(?<![A-Za-z0-9._%+\\-]))([A-Za-z0-9._%+-]{1,64})@"
                   rb"((?:[A-Za-z0-9-]+\.)+([A-Za-z]{2,24}))(?![A-Za-z0-9-])")
EMAIL_KEEP_LOCAL = {b"git", b"noreply", b"no-reply", b"donotreply", b"do-not-reply"}
EMAIL_KEEP_DOMAIN = (b"example.com", b"example.org", b"example.net", b"noreply.github.com", b"localhost")
EMAIL_KEEP_TLD = {t.encode() for t in (
    "example", "test", "invalid", "local", "localhost", "png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "js", "mjs",
    "cjs", "ts", "tsx", "jsx", "css", "scss", "json", "md", "py", "html", "txt", "pdf", "zip", "lock", "yml", "yaml",
    "toml", "sh", "map", "woff", "woff2", "ttf", "mp4", "mov", "mp3", "wav")}

# Numbers, in one pass. The left edge is checked in code (a lookbehind at the start makes the search several times
# slower); the right edge is in the pattern. Neither side may be glued to a word or be one dash-separated part of
# something longer, like the all-digit groups of a UUID (12345678-1234-1234-...).
NUMBERS = re.compile(
    rb"(?=[0-9+])(?:"
    rb"(?P<rrn>\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])-[1-8]\d{6})"
    rb"|(?P<card>[2-69]\d{3}(?P<s1>[- ]?)\d{4}(?P=s1)\d{4}(?P=s1)\d{4}|3[47]\d{2}(?P<s2>[- ]?)\d{6}(?P=s2)\d{5})"
    rb"|(?P<kr>(?:\+82[-. ]?|0)1[016789][-. ]?\d{3,4}[-. ]?\d{4}|0(?:2|[3-6][1-5]|70)[-. )]\d{3,4}[-. ]\d{4})"
    rb"|(?P<intl>\+(?!82)[1-9]\d{0,2}(?:[-. ]?\(?\d{1,4}\)?){2,5})"
    rb")(?![0-9A-Za-z_])(?!-[0-9A-Za-z])(?!\.\d)")
NUMBER_KIND = {"rrn": "resident number", "card": "card number", "kr": "phone", "intl": "phone"}
WORD = frozenset(b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_+")
ALNUM = frozenset(b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")


def _luhn(digits):
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = ch - 48
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def _left_edge(raw, at):
    if at == 0:
        return True
    before = raw[at - 1]
    if before in b"-.":  # 1234-5678-... inside a UUID, or the digits after a decimal point (0.4111111111111111)
        return not (at >= 2 and raw[at - 2] in ALNUM)
    if before in WORD:
        return at >= 2 and raw[at - 2] == 0x5C and before in b"nrtbf"  # \n and the like
    return True


def _pii(raw, count):
    """Masks emails and numbers in bytes; count[0] goes up by the number masked."""
    if b"@" in raw:
        def email(m):
            local, domain, tld = m.group(1), m.group(2).lower(), m.group(3).lower()
            if (local.lower() in EMAIL_KEEP_LOCAL or tld in EMAIL_KEEP_TLD
                    or any(domain == d or domain.endswith(b"." + d) for d in EMAIL_KEEP_DOMAIN)):
                return m.group(0)
            count[0] += 1
            return note("email").encode() + b"@" + m.group(2)
        raw = EMAIL.sub(email, raw)

    def number(m):
        if not _left_edge(m.string, m.start()):
            return m.group(0)
        kind = next(k for k in NUMBER_KIND if m.group(k))
        digits = bytes(ch for ch in m.group(0) if 48 <= ch <= 57)
        if kind == "card" and not _luhn(digits):
            return m.group(0)
        if kind == "intl" and not 9 <= len(digits) <= 15:
            return m.group(0)
        count[0] += 1
        return note(NUMBER_KIND[kind]).encode()
    return NUMBERS.sub(number, raw)


def redact_pii_text(text, count):
    """_pii for one decoded string."""
    out = _pii(text.encode("utf-8", "surrogatepass"), count)
    return out.decode("utf-8", "surrogatepass")


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


def _secrets_line(raw, obj):
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
    return _dump(new), n


def _dump(obj):
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _walk_pii(value, count):
    if isinstance(value, dict):
        return {k: _walk_pii(v, count) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk_pii(v, count) for v in value]
    if isinstance(value, str) and len(value) >= 6:
        return redact_pii_text(value, count)
    return value


def redact_line(raw, obj=None):
    """One JSONL line (bytes, ending in a newline) -> (bytes, number masked). Unchanged lines come back as is.
    obj is the line already parsed, when the caller has it."""
    raw, n = _secrets_line(raw, obj)
    count = [0]
    new = _pii(raw, count)
    if not count[0]:
        return raw, n
    try:
        json.loads(new)
    except ValueError:
        try:
            parsed = json.loads(raw)
        except ValueError:
            return new, n + count[0]  # It was not JSON to begin with.
        count = [0]
        new = _dump(_walk_pii(parsed, count))  # A match outside a string: mask string by string.
    return new, n + count[0]

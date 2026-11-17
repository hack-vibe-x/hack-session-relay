"""Replaces images (and other base64 attachments such as PDFs) in session lines with a short text note.

Standard library only, Python 3.9+. The same file is in client/ and server/ (a test checks they match): the
client strips before sending, and the server strips whatever an older client still sends.

    [image omitted: image/png, 245 KB]

Shapes found in real sessions:
- Claude Code: {"type": "image", "source": {"type": "base64", "media_type": ..., "data": ...}} in message content,
  tool results, toolUseResult and attachments; toolUseResult.file.base64 as a bare base64 string.
- Codex: {"type": "input_image", "image_url": "data:image/png;base64,..."}.
Anything else that is a data: URL or a long base64 string starting like an image or PDF is replaced as well.
The result is deterministic, so the same line always gives the same bytes (the client's hashes depend on it).
"""
import json
import re

VERSION = 1
# Cheap byte checks first: most lines have none of these and are never parsed again.
HINTS = (b'"base64"', b"base64,", b"iVBORw0KGg", b"/9j/", b"R0lGOD", b"UklGR", b"JVBERi")
MAGIC = (("iVBORw0KGg", "image/png"), ("/9j/", "image/jpeg"), ("R0lGOD", "image/gif"),
         ("UklGR", "image/webp"), ("JVBERi", "application/pdf"))
B64_HEAD = re.compile(r"^[A-Za-z0-9+/]{64,}")
MIN_BARE = 1000


def note(mime, b64_len):
    size = b64_len * 3 // 4
    if size >= 1024 * 1024:
        human = "%.1f MB" % (size / 1048576.0)
    else:
        human = "%d KB" % max(1, round(size / 1024.0))
    kind = "image" if (mime or "").startswith("image/") else "file"
    return "[%s omitted: %s, %s]" % (kind, mime or "unknown", human)


def _bare_mime(text):
    if len(text) < MIN_BARE or not B64_HEAD.match(text[:100]):
        return None
    for prefix, mime in MAGIC:
        if text.startswith(prefix):
            return mime
    return None


def _data_url(text):
    """('image/png', payload length) for a base64 data: URL, else None."""
    if len(text) < 256 or not text.startswith("data:"):
        return None
    head, sep, payload = text[:120].partition(";base64,")
    if not sep:
        return None
    return head[5:] or None, len(text) - len(head) - len(sep)


def _strip(value, count):
    if isinstance(value, dict):
        source = value.get("source")
        if isinstance(source, dict) and source.get("type") == "base64" and isinstance(source.get("data"), str):
            count[0] += 1
            return {"type": "text", "text": note(source.get("media_type"), len(source["data"]))}
        url = value.get("image_url")
        if value.get("type") == "input_image" and isinstance(url, str) and _data_url(url):
            mime, length = _data_url(url)
            count[0] += 1
            return {"type": "input_text", "text": note(mime, length)}
        return {k: _strip(v, count) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip(v, count) for v in value]
    if isinstance(value, str) and len(value) >= 256:
        found = _data_url(value)
        if found:
            count[0] += 1
            return note(found[0], found[1])
        mime = _bare_mime(value)
        if mime:
            count[0] += 1
            return note(mime, len(value))
    return value


def strip_obj(obj):
    """(new object, number replaced)."""
    count = [0]
    out = _strip(obj, count)
    return out, count[0]


def strip_line(raw, obj=None):
    """One JSONL line (bytes, ending in a newline) -> (bytes, number replaced). Unchanged lines come back as is."""
    if not any(h in raw for h in HINTS):
        return raw, 0
    if obj is None:
        try:
            obj = json.loads(raw)
        except ValueError:
            return raw, 0
    new, n = strip_obj(obj)
    if not n:
        return raw, 0
    return (json.dumps(new, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"), n

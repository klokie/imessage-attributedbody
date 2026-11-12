"""Decode the body text out of an iMessage/SMS ``attributedBody`` blob.

On modern macOS, the ``message`` table in ``~/Library/Messages/chat.db`` leaves
the plain ``text`` column NULL for the large majority of rows and stores the
message text only in ``attributedBody`` — a binary Apple *typedstream*
(NSArchiver) serialization of an ``NSAttributedString``. So the obvious
``SELECT text ... WHERE text LIKE ?`` finds almost nothing.

This module extracts just the body string, with **no dependencies** (stdlib
only) and in a few dozen lines. The framing, reverse-engineered from messages
that happen to carry *both* a non-empty ``text`` column and an
``attributedBody`` (so the answer is known):

    ... "NSString" <class refs> 0x2b <varint length> <UTF-8 bytes> ...

``0x2b`` (``+``) is the typedstream marker that introduces a byte string; the
length is a typedstream varint (one byte; ``0x81`` => the next 2 bytes are a
little-endian uint16, ``0x82`` => uint32). The first such string after the
string-class marker is the message body; everything after it is attribute-run
data we ignore.

Usage::

    from attributedbody import decode_attributed_body, message_text

    text = decode_attributed_body(row["attributedBody"])
    text = message_text(row["text"], row["attributedBody"])  # prefer plain text

MIT licensed. See README for a chat.db example and validation notes.
"""
from __future__ import annotations

__all__ = ["decode_attributed_body", "message_text"]
__version__ = "1.0.0"

_MARKER = 0x2B  # '+' : typedstream byte-string marker


def _read_varint(b: bytes, p: int) -> tuple[int, int]:
    """Read a typedstream length varint at offset ``p``; return (value, next_p)."""
    n = b[p]
    p += 1
    if n == 0x81:
        return int.from_bytes(b[p:p + 2], "little"), p + 2
    if n == 0x82:
        return int.from_bytes(b[p:p + 4], "little"), p + 4
    return n, p  # 0x00..0x80 fit in the single byte


def decode_attributed_body(blob: "bytes | memoryview | None") -> "str | None":
    """Return the message body text from an ``attributedBody`` blob, or None.

    Accepts ``bytes``, a ``memoryview`` (e.g. a sqlite3 BLOB), or ``None``.
    Returns ``None`` when the blob is empty or no body string can be extracted.
    """
    if not blob:
        return None
    b = bytes(blob)

    # Anchor on the string class declaration, then take the first 0x2b-introduced
    # byte string after it (class names are stored as plain ASCII; the body is
    # the first actual string *value*).
    anchor = b.find(b"NSString")
    if anchor == -1:
        anchor = b.find(b"NSMutableString")
    start = anchor + 8 if anchor != -1 else 0

    p = b.find(bytes([_MARKER]), start)
    while p != -1:
        try:
            length, q = _read_varint(b, p + 1)
            if 0 < length <= len(b) - q:
                try:
                    return b[q:q + length].decode("utf-8")
                except UnicodeDecodeError:
                    pass  # not the body string — keep scanning
        except IndexError:
            break
        p = b.find(bytes([_MARKER]), p + 1)
    return None


def message_text(text: "str | None", attributed_body: "bytes | None") -> "str | None":
    """Prefer the plain ``text`` column; fall back to decoding ``attributedBody``."""
    if text:
        return text
    return decode_attributed_body(attributed_body)


if __name__ == "__main__":
    # Zero-data demo: build a blob with the real framing and decode it.
    def _fixture(s: str) -> bytes:
        body = s.encode("utf-8")
        n = len(body)
        if n < 0x80:
            length = bytes([n])
        elif n < 0x1_0000:
            length = b"\x81" + n.to_bytes(2, "little")
        else:
            length = b"\x82" + n.to_bytes(4, "little")
        return (b"\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84"
                b"NSString\x01\x94\x84\x01" + bytes([_MARKER]) + length + body
                + b"\x86\x84\x02iI\x00")

    for sample in ["Haha", "Yes of course!", "\U0001f389 . Thanks", "x" * 200]:
        got = decode_attributed_body(_fixture(sample))
        print(f"{got == sample}  {got!r}")

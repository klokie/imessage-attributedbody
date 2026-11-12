"""Tests for the attributedBody decoder — synthetic blobs only, no real data.

Each fixture is built to the same typedstream framing real ``attributedBody``
blobs use, so the decoder is exercised (including both varint paths and
multibyte text) without anyone's Messages database.
"""
import unittest

from attributedbody import decode_attributed_body, message_text

_MARKER = 0x2B


def make_blob(text: str, *, string_class: bytes = b"NSString",
              trailing: bytes = b"\x86\x84\x02iI\x00") -> bytes:
    """Construct a blob with the real framing: ...<class> 0x2b <varint> <utf8>..."""
    body = text.encode("utf-8")
    n = len(body)
    if n < 0x80:
        length = bytes([n])
    elif n < 0x1_0000:
        length = b"\x81" + n.to_bytes(2, "little")
    else:
        length = b"\x82" + n.to_bytes(4, "little")
    header = b"\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84"
    refs = b"\x01\x94\x84\x01"  # class-ref bytes seen before the 0x2b in real blobs
    return header + string_class + refs + bytes([_MARKER]) + length + body + trailing


class TestDecoder(unittest.TestCase):
    def test_short_strings(self):
        for s in ["Haha", "Yes!", "Yes of course!", "I need help with this"]:
            self.assertEqual(decode_attributed_body(make_blob(s)), s)

    def test_long_string_uses_two_byte_varint(self):
        s = "x" * 200  # > 127 -> 0x81 + uint16 length path
        self.assertEqual(decode_attributed_body(make_blob(s)), s)

    def test_very_long_string(self):
        s = "word " * 1000  # 5000 bytes, still uint16 path
        self.assertEqual(decode_attributed_body(make_blob(s)), s)

    def test_multibyte_and_emoji(self):
        for s in ["\U0001f389 . Thanks", "café ☕ naïve", "日本語のメッセージ"]:
            self.assertEqual(decode_attributed_body(make_blob(s)), s)

    def test_body_containing_plus_sign(self):
        s = "a+b = c"  # the 0x2b inside the body must not confuse the scan
        self.assertEqual(decode_attributed_body(make_blob(s)), s)

    def test_mutable_string_class(self):
        s = "sent from an NSMutableString"
        self.assertEqual(
            decode_attributed_body(make_blob(s, string_class=b"NSMutableString")), s
        )

    def test_none_and_empty(self):
        self.assertIsNone(decode_attributed_body(None))
        self.assertIsNone(decode_attributed_body(b""))
        self.assertIsNone(decode_attributed_body(memoryview(b"")))

    def test_no_string_marker(self):
        self.assertIsNone(decode_attributed_body(b"\x04\x0bstreamtyped no body here"))

    def test_memoryview_input(self):
        s = "from a sqlite BLOB"
        self.assertEqual(decode_attributed_body(memoryview(make_blob(s))), s)

    def test_message_text_prefers_plain(self):
        self.assertEqual(message_text("plain wins", make_blob("blob")), "plain wins")
        self.assertEqual(message_text(None, make_blob("blob")), "blob")
        self.assertEqual(message_text("", make_blob("blob")), "blob")


if __name__ == "__main__":
    unittest.main(verbosity=2)

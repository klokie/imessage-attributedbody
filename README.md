# imessage-attributedbody

Decode the body text out of an iMessage/SMS **`attributedBody`** blob — in one
small, dependency-free Python file.

## The problem

On modern macOS, the `message` table in `~/Library/Messages/chat.db` leaves the
plain **`text`** column `NULL` for the large majority of messages and stores the
text only in the binary **`attributedBody`** column — an Apple *typedstream*
(NSArchiver) serialization of an `NSAttributedString`.

So the obvious query finds almost nothing:

```sql
SELECT text FROM message WHERE text LIKE '%dinner%';  -- misses ~98% of messages
```

On a real database the split is stark — on one 154k-message store:

| text storage | messages |
| --- | ---: |
| plain `text` column | ~1,400 |
| only `attributedBody` | ~151,500 |

You have to decode `attributedBody` to search or export your messages. This does
exactly that, and nothing else.

## Install

It's a single file with **no dependencies** — vendor it, or install it:

```bash
pip install imessage-attributedbody        # provides the `attributedbody` module
# or just copy attributedbody.py into your project
```

## Usage

```python
from attributedbody import decode_attributed_body, message_text

text = decode_attributed_body(blob)            # bytes | memoryview | None -> str | None
text = message_text(row["text"], row["attributedBody"])  # prefer plain text, fall back
```

### With chat.db

```python
import sqlite3, os
from attributedbody import message_text

db = os.path.expanduser("~/Library/Messages/chat.db")
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)   # read-only
for text, blob in con.execute("SELECT text, attributedBody FROM message LIMIT 20"):
    print(message_text(text, blob))
```

Reading `chat.db` requires **Full Disk Access** for your terminal/app
(System Settings → Privacy & Security → Full Disk Access). Open it read-only
(`mode=ro`) — it's a live database owned by Messages.

## How it works

The text is framed inside the typedstream like this:

```
... "NSString" <class refs> 0x2b <varint length> <UTF-8 bytes> ...
```

`0x2b` (`+`) is the typedstream marker that introduces a byte string; the length
is a typedstream varint (one byte, or `0x81`+uint16 / `0x82`+uint32 for longer
strings). The decoder anchors on the string-class marker and returns the first
such string — the message body. That's the whole trick; the implementation is
~40 lines.

## Validation

The synthetic tests (`test_attributedbody.py`) build blobs to the real framing —
short and long strings (both varint paths), emoji/multibyte, a `+` inside the
body, `NSMutableString`, `memoryview` input, `None`/empty — with **no real
message data**, so they run anywhere:

```bash
python -m unittest test_attributedbody.py
python attributedbody.py        # zero-data demo
```

The framing was reverse-engineered from messages carrying *both* a non-empty
`text` column and an `attributedBody` (so the expected output is known), and the
decoder matches **100%** of those ground-truth messages on the author's own
database (~1,400 of them). Your messages never leave your machine to verify it —
point the snippet in [Validation] at your own `chat.db`.

## Scope / alternatives

This decodes **message body text** — the thing you need for search, CRM
"last contacted" signals, or a lightweight export. It does not parse attribute
runs, mentions, or link previews. For a full-featured, battle-tested exporter
(attachments, reactions, HTML/PDF output) see
[`imessage-exporter`](https://github.com/ReagentX/imessage-exporter) (Rust).

## Bonus gotcha (if you're building a search index)

If you load the decoded text into a **SQLite FTS5 external-content table**
(`content='...'`), a plain `INSERT ... SELECT` does **not** build the index —
and `SELECT COUNT(*)` mirrors the content table, so it *looks* populated while
`MATCH` returns nothing. Build it with the rebuild command:

```sql
INSERT INTO messages_fts(messages_fts) VALUES('rebuild');
```

## License

MIT © 2026 Daniel Grossfeld

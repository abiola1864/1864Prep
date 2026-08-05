# Reading messy files, and cleaning natural language

Two capabilities that make the engine robust to *how* data arrives, not just
what's in it.

## Robust ingestion — `engine/ingest.py`

`read_any(path)` reads a file into a clean table and returns a report of what it
detected, so nothing happens invisibly. It handles:

- **CSV / TSV / TXT** — sniffs the character encoding (so odd encodings don't
  turn into gibberish), sniffs the delimiter by *consistency across lines* (not
  fooled by a title banner at the top), skips banner/metadata rows to find the
  real header, and pads or trims ragged rows to a consistent width.
- **Excel** (`.xlsx/.xls/.xlsm`) — reads every sheet, picks the fullest one, and
  detects the header row inside it.
- **JSON** — flattens nested objects into dotted columns (`person.name`).
- **PDF** — extracts ruled tables with `pdfplumber` and merges tables that span
  pages; if there are no ruled tables, it falls back to text lines and flags them
  for review.

```python
from engine.ingest import read_any
df, report = read_any("some_export.pdf")
print(report.summary())   # e.g. "pdf | 320 rows x 6 cols | 4 pdf tables | merged 4 tables across 3 pages"
```

**Honest limit:** scanned/image PDFs (photos of documents) need OCR (Tesseract),
which is a system dependency and a separate module on the roadmap — the current
PDF reader works on digital PDFs with selectable text/tables.

## Natural-language / free-text cleaning — `engine/textclean.py`

Free-text fields carry the worst mess. All of this is deterministic and local:

- `normalize_text` — repairs broken encodings (mojibake like `Ã©` → `é`, via
  `ftfy`), strips zero-width and control characters, normalises smart quotes and
  dashes, and collapses runaway whitespace. It never changes meaning.
- `normalize_missing` — treats the many spellings of "missing" (`N/A`, `NULL`,
  `-`, `unknown`, …) as blank.
- `detect_language` — best-effort language of a column (via `langdetect`).
- `extract(kind, text)` — pulls **emails, phones, dates, or long ID-like numbers**
  out of prose with regex, for when structured values are buried in a notes field.

The `text_clean` transform applies the safe normalisation across a column.

**Honest limit:** deeper NLP — named-entity recognition, semantic parsing of
addresses, meaning-based synonym matching — needs a model. That is the optional
**AI layer**, not this module. What's here is the deterministic floor that runs
with no account and no internet.

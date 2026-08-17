# 1864 Prep — the robust pipeline (v2)

The v1 pipeline decided with chains of `if` conditions, which fight each other on
odd files. v2 replaces that with one principle applied everywhere:

> **Gather evidence → score every candidate → commit only above a confidence
> threshold, otherwise ask the person.** Never a single brittle test; always a
> weighted vote with a human fallback.

Nothing is ever decided by one signal. Every stage produces *candidates with
scores and reasons*, a *winner*, and a *confidence*. Low confidence is not a
failure — it routes to review with the candidates shown. This removes the
contradictions, because signals are combined, not chained.

Two things still flow end to end (from v1): the **Context** object and the
**Decisions ledger**. v2 adds a **Confidence** to every entry.

```
detect ─▶ score ─▶ commit (high conf)  ┐
                └▶ ask the person (low conf) ┘ ─▶ next stage
```

---

## Part A — The universal resolver

Every decision in the engine (encoding, delimiter, header row, orientation,
column type, a value fix) uses the same shape:

```
Candidate  { value, score, evidence[] }
Resolve(candidates, threshold):
    rank by score
    if top.score - second.score >= margin AND top.score >= threshold:
        commit(top)                      # confident
    else:
        review(candidates)               # show options, let the person choose
```

- **Scores are additive evidence**, capped and normalised — not booleans. A date
  order gets +weight for each row that fits, −weight for each that breaks it.
- **Precedence is encoded as weights**, so a strong signal (an Excel merged-cell
  range; an explicit `sep=;` line; a BOM) simply outweighs weak ones, instead of
  an `if` short-circuiting the rest.
- **A margin requirement** stops near-ties from committing: two plausible delimiters
  10 points apart → ask; 500 apart → commit.
- **Every commit records its evidence** in the ledger, so a wrong auto-choice is
  visible and reversible.

This one mechanism, reused, is what makes the whole thing robust instead of a
maze of conditions.

---

## Part B — The hazard catalogs (all the data worries)

The resolver is only as good as the signals it knows to look for. These are the
real-world problems the engine must detect, per format.

### B1 · Bytes & encoding (all text formats)

- BOM present: UTF-8, UTF-16 LE/BE, UTF-32 → strip and honour it (strong signal).
- No BOM: sniff UTF-8 → UTF-16 → Windows-1252 / Latin-1 → Big5/Shift-JIS by
  byte-pattern scoring, not a fixed order.
- Mojibake / double-encoding (`Ã©`, `â€™`, `Ã¯Â¿Â½`) → repair.
- Zero-width chars, non-breaking spaces, soft hyphens, RTL/LTR marks → strip.
- Mixed line endings (`\r\n`, `\r`, `\n`), a final line with no newline.
- NUL bytes and control chars embedded in fields.
- Over-long UTF-8 sequences / invalid bytes → replace, note count.

### B2 · CSV / TSV / delimited

- Delimiter ambiguity: comma vs semicolon vs tab vs pipe vs whitespace; a
  European CSV using `;` because `,` is the decimal mark → score per-line
  consistency, honour an explicit `sep=` first line.
- Quoting: quoted fields containing the delimiter, quoted newlines (a cell that
  spans lines), doubled quotes `""`, quotes only on some fields, smart quotes.
- Ragged rows: rows with more or fewer fields than the header → pad/trim, and
  flag rows where trimming would lose data.
- Banner / title / notes rows above the header; footnote / source / total rows
  below the data; blank separator rows.
- Multiple header rows (grouped headers written as two lines).
- Two tables stacked in one file (a blank band then a second header).
- Trailing delimiter (a phantom empty last column); leading index column.
- Comment lines (`#`, `//`); a "sep=,;" Excel hint line.
- Numbers: thousands separators (`1,234` / `1.234` / `1 234`), decimal comma,
  currency symbols, percent, parentheses-negatives `(500)`, scientific `1.2E3`,
  leading-zero codes (`007`), long IDs that must stay text, Excel serial dates
  leaked as integers.
- Dates: D/M/Y vs M/D/Y ambiguity resolved from the *whole* column; 2-digit
  years; month names in any locale; mixed formats; Excel serials.
- Booleans vs flags: `y/n`, `yes/no`, `true/false`, `1/0` (real) vs single-pole
  `y` and multi-code `y,v` (not boolean).
- Placeholders for missing: `NA`, `N/A`, `-`, `.`, `null`, `999`, `-1`, `#N/A`.

### B3 · Excel (.xlsx / .xlsm / .xls / .xlsb)

- Multiple sheets; picking the primary table vs helper sheets ("check", "notes",
  "pivot"); **processing each sheet separately, never merged**.
- Legacy `.xls` (BIFF) and macro `.xlsm`; password-protected → clear message.
- **Merged cells** — group headers stored only top-left; vertically merged row
  labels → un-merge/fill from the real ranges.
- Multi-row / multi-level headers (2–3 stacked rows, some merged).
- Formula cells → read the computed value; cached vs needing recompute; `#REF!`,
  `#DIV/0!`, `#N/A` error values → treat as missing/flag.
- Numbers stored as text (green-triangle) and text stored as numbers (an ID that
  became `1.23E+11`, a code that lost leading zeros).
- Excel **date serials** and datetime, 1900 vs 1904 date systems, time-only cells.
- Cell number formats that hide the true value (a "%" display over a 0–1 float; a
  currency display; a rounded display of a longer number).
- Hidden rows/columns and sheets; grouped/outline rows; filtered (hidden by
  auto-filter) rows; frozen panes (view only).
- Auto-filter range and print area as *hints* to the real table extent.
- Blank spacer rows/columns; side-by-side tables on one sheet.
- Rich text / mixed fonts in a cell; in-cell line breaks; leading apostrophe
  text marker; hyperlinks; comments/notes.
- Charts, images, shapes floating over cells → ignore, don't read as data.
- Very large sheets / many columns → stream, cap, sample for structure.

### B4 · PDF tables

- Digital text vs **scanned image** → detect; scanned needs OCR (optional), with
  a clear "this is a scan" message and lower confidence.
- Table detection: ruled tables (lines) vs whitespace-aligned columns vs no clear
  columns → score; multi-column page layout (two article columns misread as data).
- Cells spanning columns/rows; wrapped text making one cell into several lines;
  a row split across a page break; repeated headers on every page.
- Headers/footers, page numbers, watermarks, footnotes bleeding into the table.
- Rotated pages / landscape; right-to-left scripts; ligatures and CID fonts that
  extract as garbage; hidden text layers.
- Numbers glued to units, currency, or footnote markers; decimal alignment used
  instead of a real decimal point.
- Multiple tables per page / one table across many pages → stitch by matching
  column signatures, not by page.

### B5 · JSON (and NDJSON / JSONL)

- Shape: array of objects (rows) vs single object vs nested object vs an object
  whose values are the records vs NDJSON (one object per line).
- Ragged keys: objects with different key sets → union the columns, fill missing.
- Nesting: nested objects → flatten with dotted paths; arrays inside a field →
  keep as a value, or explode to rows (a choice, shown).
- Type drift: the same key is a number in one row, a string in another, null in a
  third → resolve to one type or flag.
- Numbers as strings; booleans as `"true"`; dates as ISO strings or epochs
  (seconds vs milliseconds); big integers that lose precision.
- Deeply nested / huge documents → stream (ijson-style), cap depth, sample.
- Encoding, BOM, and trailing commas / comments in "JSON" that is really JSON5.
- A metadata wrapper (`{"data":[...], "meta":{...}}`) → find the records array.

---

## Part C — The stages, made robust

Each stage is the resolver over the relevant hazards. Order is fixed;
*within* a stage nothing is chained — signals are scored together.

### Stage 0 · Acquire & sniff
Read bytes (streaming if large). Resolve **encoding** and **line endings** (B1).
For a container (`.zip`, `.gz`) unwrap first. Output: clean text/grid + encoding
confidence.

### Stage 1 · Format & shape
Resolve the **format** (extension is a hint, not proof — sniff magic bytes) and
its top-level **shape** (B2/B3/B4/B5): which sheets, is JSON an array or wrapped,
is the PDF scanned. Per Excel sheet and per JSON records-array, continue
independently.

### Stage 2 · Table extent & structure
Resolve, by score, in this dependency order (each feeds the next, no back-and-forth):
1. **Delimiter/columns** (CSV) or grid (Excel/PDF/JSON).
2. **Data region** — where do real records start (mixed text+numbers, confirmed by
   neighbours), skipping banners/footers/totals.
3. **Header band** — the rows just above data; exclude banner-width rows; use
   merged-cell ranges and auto-filter extent as strong hints.
4. **Orientation** — normal / transposed / form, from width-vs-height, first-column
   label-ness, and type homogeneity down columns vs across rows.
5. **Compose headers** — merge multi-row headers into one clear name per column.
6. **Drop** blank spacer rows/columns; **split** stacked tables.
Low confidence at any step → the structure-review screen, candidates shown.

### Stage 3 · Column identity
Per column, over the *whole* column: resolve **semantic type** and **expected
values** (B2 numbers/dates/booleans/codes; reference lists; ranges; patterns),
with look-alike guards (code≠number, flag≠boolean, id≠phone). Output a per-column
Context entry with evidence and a confidence.

### Stage 4 · Header review (first, human)
Show structure + per-column identity + confidence. The person confirms names,
types, orientation, sheet(s). Anything the resolver flagged as low-confidence is
highlighted for a decision. Nothing was value-cleaned yet.

### Stage 5 · Plan → Stage 6 · Decide → Stage 7 · Apply & verify
As v1, but every action carries its evidence and confidence; safe formatting is
auto+listed, meaning-changes are shown severally, and after applying, each column
is **re-validated against its expected contract**; residuals are flagged, not hidden.

### Stage 8 · Insight → Stage 9 · Export
Before/after distributions; export clean data (multi-sheet preserved) + the full
ledger, and optionally a reusable **template** (the confirmed structure + types)
so the next file of the same shape skips to review.

---

## Part D · Why this is robust (and not contradictory)

- **One resolver, many uses.** Encoding, delimiter, header, orientation, type, and
  value fixes all use the same score-and-gate mechanism, so behaviour is uniform
  and testable, not a per-case `if` thicket.
- **Signals combine, they don't override each other.** A strong structural fact
  (merged ranges, `sep=`, BOM) is a large weight, not a short-circuit; weak signals
  still contribute. No two conditions can contradict — they add into one score.
- **Confidence + margin gate every commit.** Ties and weak wins go to the person
  instead of guessing, which is exactly where v1 produced nonsense.
- **The whole column, always.** Types and formats are decided from the full column,
  so one odd cell can never flip the rest.
- **Human review is a first-class outcome**, not an error path. It is where
  ambiguity is meant to land, with candidates and evidence shown.
- **Every decision is logged with its evidence**, so any auto-choice is auditable
  and reversible.

## Part E · Build order

1. The **universal resolver** (Candidate/score/gate) + Confidence in the ledger.
2. Re-express existing detectors (encoding, delimiter, header, orientation, type)
   as resolvers feeding it — removing the chained `if`s.
3. Fill the **hazard catalogs** as scored signals, format by format
   (CSV → Excel → JSON → PDF), each with tests built from the catalog.
4. Wire **structure-review + header-review** as the low-confidence destination.
5. Streaming/sampling for large CSV/Excel/JSON; OCR path for scanned PDF (optional).

"""Robust ingestion — read messy inputs of many kinds into a clean DataFrame.

Real agency files are rarely tidy: unknown encodings, odd delimiters, banner
rows before the real header, multi-sheet workbooks, nested JSON exports, and
data trapped in PDF tables. `read_any` handles these and returns both the table
and a small report of what it detected, so nothing happens invisibly.

Supported: .csv .tsv .txt  |  .xlsx .xls .xlsm  |  .json  |  .pdf

Not handled here (documented in the roadmap): scanned/image PDFs need OCR
(Tesseract), which requires a system dependency and is a separate module.
"""
from __future__ import annotations

import re
import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class IngestReport:
    path: str
    kind: str
    encoding: str | None = None
    delimiter: str | None = None
    header_row: int | None = None
    sheet: str | None = None
    sheets_found: list[str] = field(default_factory=list)
    pages: int | None = None
    tables_found: int | None = None
    rows: int = 0
    cols: int = 0
    notes: list[str] = field(default_factory=list)
    skipped_rows: list[str] = field(default_factory=list)

    def summary(self) -> str:
        bits = [f"{self.kind}", f"{self.rows} rows x {self.cols} cols"]
        if self.encoding: bits.append(f"encoding={self.encoding}")
        if self.delimiter: bits.append(f"delimiter={self.delimiter!r}")
        if self.header_row: bits.append(f"header at row {self.header_row}")
        if self.sheet: bits.append(f"sheet={self.sheet!r}")
        if self.tables_found is not None: bits.append(f"{self.tables_found} pdf tables")
        return " | ".join(bits)


# ---------------------------------------------------------------------------
def _sniff_encoding(raw: bytes) -> str:
    # BOM is the most reliable signal (charset detectors often miss UTF-16).
    if raw[:2] == b"\xff\xfe":
        return "utf-16-le"
    if raw[:2] == b"\xfe\xff":
        return "utf-16-be"
    if raw[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    try:
        from charset_normalizer import from_bytes
        m = from_bytes(raw).best()
        if m is not None:
            return m.encoding
    except Exception:
        pass
    # last resort: latin-1 never fails to decode, so a mangled file still loads
    try:
        raw.decode("utf-8")
        return "utf-8"
    except Exception:
        return "latin-1"


def _sniff_delimiter(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()][:30]
    best, best_score = ",", -1
    for d in [",", ";", "\t", "|"]:
        counts = [ln.count(d) for ln in lines]
        nonzero = [c for c in counts if c > 0]
        if not nonzero:
            continue
        modal = max(set(nonzero), key=nonzero.count)      # most common per-line count
        consistency = sum(1 for c in counts if c == modal)  # lines that agree
        score = consistency * modal                          # agreement x columns
        if score > best_score:
            best, best_score = d, score
    return best


def _row_num_share(row: list[str]) -> float:
    vals = [str(c).strip() for c in row if str(c).strip()]
    if not vals:
        return 0.0
    return sum(1 for v in vals if _looks_numeric(v)) / len(vals)


def _find_data_start(rows: list[list[str]]) -> int:
    """First row that looks like real data: several non-empty cells, a mix of
    text and numbers, and the row below it looks similar. Banner/title lines and
    header rows (all-text, or very sparse) are skipped."""
    for i in range(len(rows) - 1):
        row = [str(c).strip() for c in rows[i]]
        ne = [c for c in row if c]
        if len(ne) < 3:
            continue
        share = _row_num_share(row)
        if not (0.15 <= share <= 0.95):          # data has both labels and numbers
            continue
        nxt = [str(c).strip() for c in rows[i + 1]]
        if len([c for c in nxt if c]) >= 3 and 0.0 <= _row_num_share(nxt) <= 0.95:
            return i
    return -1


def _header_band(rows: list[list[str]], data_start: int) -> tuple[int, int]:
    """The header is the block of consecutive non-blank rows sitting just above
    the first data row, after skipping any blank separator. Rows far narrower than
    the data (banners/titles) are excluded even without a blank separator."""
    data_ne = sum(1 for c in rows[data_start] if str(c).strip()) if data_start < len(rows) else 1
    floor = max(2, data_ne * 0.5)
    j = data_start - 1
    while j >= 0 and not any(str(c).strip() for c in rows[j]):   # skip blank separators
        j -= 1
    end = j
    while j >= 0:
        ne = sum(1 for c in rows[j] if str(c).strip())
        if ne == 0 or ne < floor:                               # blank OR banner-width -> stop
            break
        j -= 1
    start = j + 1
    if end < start:
        return max(0, data_start - 1), max(0, data_start - 1)
    if end - start + 1 > 3:                                      # cap at 3 header rows nearest data
        start = end - 2
    return start, end


def _detect_header_row(rows: list[list[str]]) -> int:
    """Best-effort single header row (fallback when there is no clear data
    region). Mostly non-empty, mostly non-numeric, followed by a similar row."""
    best, best_score = 0, -1.0
    for i, row in enumerate(rows[:15]):
        cells = [c.strip() for c in row]
        nonempty = [c for c in cells if c != ""]
        if len(nonempty) < 2:
            continue
        nonnumeric = sum(1 for c in nonempty if not _looks_numeric(c))
        width_next = len(rows[i + 1]) if i + 1 < len(rows) else len(row)
        width_match = 1.0 if abs(width_next - len(row)) <= 1 else 0.4
        score = (len(nonempty) / max(1, len(cells))) * (nonnumeric / len(nonempty)) * width_match
        if score > best_score:
            best, best_score = i, score
    return best


def _looks_numeric(s: str) -> bool:
    s = s.replace(",", "").replace("%", "").replace("$", "").strip()
    try:
        float(s)
        return True
    except ValueError:
        return False


def _compose_multi(levels: list[list[str]], forward_fill: bool = True) -> list[str]:
    """Turn 1-3 stacked header rows into one name per column, predictably.

    When merged cells have already been filled in (xlsx), pass forward_fill=False
    so a single-cell label is not smeared across neighbours. For CSVs, where
    merge info is lost, forward_fill=True approximates merged parents. Each
    column's name is its distinct labels joined top-to-bottom, e.g. 'Sales - total'.
    """
    def norm(v):
        return re.sub(r"\s+", " ", str(v).replace("\n", " ")).strip()
    width = max((len(l) for l in levels), default=0)
    filled = []
    for depth, lvl in enumerate(levels):
        row = [norm(c) for c in lvl] + [""] * (width - len(lvl))
        if forward_fill and depth < len(levels) - 1:      # approximate merged parents (CSV only)
            ff, last = [], ""
            for c in row:
                if c:
                    last = c
                ff.append(c if c else last)
            row = ff
        filled.append(row)
    out = []
    for j in range(width):
        parts = []
        for depth in range(len(filled)):
            v = filled[depth][j]
            if v and (not parts or parts[-1] != v):
                parts.append(v)
        out.append(" - ".join(parts))
    return out


def _resolve_header(rows: list[list[str]], hdr: int, forward_fill: bool = True) -> tuple[list[str], int]:
    """Return (column_names, first_data_row_index). Anchors on the first data
    row and composes the 1-3 header rows above it. Falls back to the single
    detected header row when no clear data region is found."""
    data_start = _find_data_start(rows)
    if data_start > 0:
        start, end = _header_band(rows, data_start)
        levels = [rows[k] for k in range(start, end + 1)]
        if levels:
            return _compose_multi(levels, forward_fill=forward_fill), data_start
    return [re.sub(r"\s+", " ", str(rows[hdr][j] if j < len(rows[hdr]) else "").replace("\n", " ")).strip()
            for j in range(len(rows[hdr]))], hdr + 1


def _drop_empty_columns(df: pd.DataFrame, notes: list) -> pd.DataFrame:
    """Remove columns that hold no data at all (blank spacer columns common in
    spreadsheet exports). Reported, never silent."""
    keep = [c for c in df.columns if df[c].astype(str).str.strip().replace("nan", "").ne("").any()]
    dropped = len(df.columns) - len(keep)
    if dropped:
        notes.append(f"removed {dropped} empty column(s)")
    return df[keep]


MAX_BYTES = 60 * 1024 * 1024          # hard cap; above this we sample + batch
_SAMPLE_ROWS = 5000                    # rows scanned for structure/type detection on huge files


def detect_orientation(rows: list[list[str]]) -> str:
    """Decide how the table is laid out so headers always end up as columns.
    Conservative: only leaves 'normal' when there is a strong signal otherwise.

    'normal'     header across the top (keep).
    'transposed' field names down the first column, records left-to-right (transpose).
    'form'       first column(s) hold category/section labels and sub-totals.
    """
    body = [r for r in rows if any(str(c).strip() for c in r)]
    if len(body) < 3:
        return "normal"
    ncols = max(len(r) for r in body)
    if ncols < 2:
        return "normal"

    def numshare(cells):
        v = [str(c).strip() for c in cells if str(c).strip()]
        return sum(1 for x in v if _looks_numeric(x)) / len(v) if v else 0.0

    # FORM: 'total/subtotal/section/category' labels appear in the first two
    # columns, and many rows are otherwise blank (a template, not a table).
    label_words = re.compile(r"\b(total|subtotal|sub-total|category|section|item|justification)\b", re.I)
    left_labels = [str(r[k]).strip() for r in body for k in (0, 1) if k < len(r) and str(r[k]).strip()]
    label_hits = sum(1 for v in left_labels if label_words.search(v))
    mostly_blank = sum(1 for r in body if sum(1 for c in r[2:] if str(c).strip()) <= 1)
    if label_hits >= 2 and mostly_blank >= len(body) * 0.3:
        return "form"

    # TRANSPOSED: strong signal = wide and short (more record-columns than field-
    # rows), the first column is all text (field names), and it's more distinct than
    # the first row. Requiring width > height avoids mislabelling normal tables.
    col0 = [str(r[0]).strip() for r in body if r]
    col0_num = numshare(col0)
    row0_num = numshare(body[0])
    if ncols >= len(body) * 1.3 and col0_num < 0.1 and row0_num < 0.35:
        col0_distinct = len(set(v.lower() for v in col0 if v)) / max(1, len([v for v in col0 if v]))
        if col0_distinct > 0.8:
            return "transposed"
    return "normal"


def read_csv_like(path: Path, kind: str) -> tuple[pd.DataFrame, IngestReport]:
    size = path.stat().st_size
    raw = path.read_bytes()
    enc = _sniff_encoding(raw[:1 << 20])                    # sniff on first 1MB only
    text = raw.decode(enc, errors="replace")
    delim = "\t" if kind == "tsv" else _sniff_delimiter(text[:1 << 16])
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows, truncated = [], False
    for i, r in enumerate(reader):
        rows.append(r)                                       # keep blanks: they mark separators
        if size > MAX_BYTES and len(rows) >= _SAMPLE_ROWS:
            truncated = True
            break
    while rows and not any(str(c).strip() for c in rows[-1]):
        rows.pop()                                           # trim trailing blank lines only
    hdr = _detect_header_row([r for r in rows if any(str(c).strip() for c in r)])
    header, data_start = _resolve_header(rows, hdr)          # multi-row header on CSV too
    header = [str(c).strip() or f"column_{j+1}_no_header" for j, c in enumerate(header)]
    orient = detect_orientation([r for r in rows[data_start:data_start + 200] if any(str(c).strip() for c in r)])
    width = len(header)
    body = [(r + [""] * width)[:width] for r in rows[data_start:] if any(str(c).strip() for c in r)]
    df = pd.DataFrame(body, columns=_dedupe_headers(header))
    if orient == "transposed":
        df = _transpose(df)
    rep = IngestReport(str(path), kind, encoding=enc, delimiter=delim, header_row=data_start,
                       rows=len(df), cols=len(df.columns))
    rep.notes.append(f"layout detected: {orient}")
    if data_start > 0:
        rep.skipped_rows = [" · ".join(c.strip() for c in rows[k] if c.strip()) for k in range(min(data_start, hdr + 1))]
    if truncated:
        rep.notes.append(f"large file ({size // (1024*1024)} MB): structure read from the first {_SAMPLE_ROWS} rows; run full clean in batches")
    return df, rep


def _transpose(df: pd.DataFrame) -> pd.DataFrame:
    """Flip a table whose field names run down the first column into one whose
    field names are the columns."""
    if df.empty:
        return df
    idx = df.columns[0]
    t = df.set_index(idx).T.reset_index(drop=True)
    t.columns = [str(c).strip() or f"column_{i+1}_no_header" for i, c in enumerate(t.columns)]
    t.columns = _dedupe_headers(list(t.columns))
    return t


_HELPER_SHEET = re.compile(r"\b(check|notes?|readme|meta(data)?|temp|tmp|qa|pivot|lookup|drop.?down|list|ref|scratch|working|calc)\b", re.I)


def _sheet_density(raw: list[list[str]]) -> float:
    """How rectangular the data region is: fraction of cells that are non-empty
    across rows that look like data. A clean single table scores high; a sheet
    with spacer columns or side-by-side copies scores low."""
    data = [r for r in raw if sum(1 for c in r if str(c).strip()) >= 2]
    if not data:
        return 0.0
    width = max(len(r) for r in data)
    filled = sum(1 for r in data for c in r if str(c).strip())
    return filled / max(1, len(data) * width)


def _unmerge_fill(grid: list[list[str]], merged) -> list[list[str]]:
    """Fill merged spans so a group label reaches every cell it visually covers
    (Excel stores it only in the top-left cell; pandas leaves the rest blank)."""
    try:
        from openpyxl.utils import range_boundaries
    except Exception:
        return grid
    for rng in merged:
        min_c, min_r, max_c, max_r = range_boundaries(str(rng))   # 1-based
        if min_r - 1 >= len(grid) or min_c - 1 >= len(grid[min_r - 1]):
            continue
        val = grid[min_r - 1][min_c - 1]
        if not str(val).strip():
            continue
        for r in range(min_r - 1, min_r):        # fill header spans (top-left across its block)
            pass
        for r in range(min_r - 1, max_r):
            for c in range(min_c - 1, max_c):
                if r < len(grid) and c < len(grid[r]) and not str(grid[r][c]).strip():
                    grid[r][c] = val
    return grid


def _read_one_sheet(path: Path, sheet: str, grid: list[list[str]], sheets: list[str]) -> tuple[pd.DataFrame, IngestReport]:
    """Clean a single sheet in isolation (never merged with another sheet)."""
    merged, autofilter, freeze = [], None, None
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb[sheet]
        merged = list(ws.merged_cells.ranges)
        autofilter = ws.auto_filter.ref
        freeze = ws.freeze_panes
    except Exception:
        pass

    raw = _unmerge_fill([list(map(str, r)) for r in grid], merged)
    raw = [r for r in raw if any(str(c).strip() for c in r)]
    hdr = _detect_header_row([[str(c) for c in r] for r in raw])
    header, data_start = _resolve_header(raw, hdr, forward_fill=(not merged))
    header = [str(c).strip() or f"column_{j+1}_no_header" for j, c in enumerate(header)]
    body = [(list(map(str, r)) + [""] * len(header))[:len(header)] for r in raw[data_start:]]
    df = pd.DataFrame(body, columns=_dedupe_headers(header))
    df = _drop_empty_columns(df, rep_notes := [])
    orient = detect_orientation(raw[data_start:data_start + 200])
    if orient == "transposed":
        df = _transpose(df)
    rep = IngestReport(str(path), "xlsx", sheet=sheet, sheets_found=sheets,
                       header_row=data_start, rows=len(df), cols=len(df.columns))
    rep.notes.extend(rep_notes)
    rep.notes.append(f"layout detected: {orient}")
    if merged:
        rep.notes.append(f"filled {len(merged)} merged cell block(s) so group headers reach every column")
    if autofilter:
        rep.notes.append(f"sheet had an auto-filter over {autofilter}")
    if freeze:
        rep.notes.append(f"sheet had frozen panes at {freeze} (view only; data unaffected)")
    return df, rep


def read_all_sheets(path: Path) -> list[tuple[str, pd.DataFrame, IngestReport]]:
    """Clean EVERY sheet independently, preserving names and count. Sheets are
    never merged into one table; each keeps its own structure and header."""
    xl = pd.ExcelFile(path)
    sheets = xl.sheet_names
    out = []
    for s in sheets:
        grid = xl.parse(s, header=None, dtype=str).fillna("").values.tolist()
        df, rep = _read_one_sheet(path, s, grid, sheets)
        out.append((s, df, rep))
    return out


def read_excel(path: Path, sheet: str | None = None) -> tuple[pd.DataFrame, IngestReport]:
    """Read one sheet. Honours an explicit `sheet`; otherwise picks the cleanest
    primary table (skipping helper sheets like 'check'/'notes'). Use
    read_all_sheets() to process a whole workbook sheet by sheet."""
    xl = pd.ExcelFile(path)
    sheets = xl.sheet_names
    grids = {s: xl.parse(s, header=None, dtype=str).fillna("").values.tolist() for s in sheets}
    if sheet and sheet in grids:
        best = sheet
    else:
        def score(s):
            name_penalty = 0.6 if _HELPER_SHEET.search(s) else 1.0
            return _sheet_density(grids[s]) * name_penalty
        best = max(sheets, key=score)
    df, rep = _read_one_sheet(path, best, grids[best], sheets)
    if len(sheets) > 1:
        others = [s for s in sheets if s != best]
        rep.notes.insert(0, f"{len(sheets)} sheets; cleaned {best!r} (others: {', '.join(map(repr, others))}). "
                            f"Process every sheet to keep them all.")
    return df, rep


def read_json(path: Path) -> tuple[pd.DataFrame, IngestReport]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        # find the first list-of-records value, else wrap the dict
        rec = next((v for v in data.values() if isinstance(v, list)), None)
        data = rec if rec is not None else [data]
    df = pd.json_normalize(data)              # flattens nested keys to a.b.c
    df = df.astype(object).where(df.notna(), "")
    rep = IngestReport(str(path), "json", rows=len(df), cols=len(df.columns))
    if any("." in str(c) for c in df.columns):
        rep.notes.append("flattened nested JSON keys with dot notation")
    return df, rep


def read_pdf(path: Path) -> tuple[pd.DataFrame, IngestReport]:
    import pdfplumber
    tables, npages = [], 0
    with pdfplumber.open(path) as pdf:
        npages = len(pdf.pages)
        for page in pdf.pages:
            for t in (page.extract_tables() or []):
                if t and len(t) >= 2:
                    tables.append(t)
    rep = IngestReport(str(path), "pdf", pages=npages, tables_found=len(tables))
    if not tables:
        # no ruled tables — fall back to whitespace-delimited text lines
        with pdfplumber.open(path) as pdf:
            lines = []
            for page in pdf.pages:
                txt = page.extract_text() or ""
                lines += [ln for ln in txt.splitlines() if ln.strip()]
        rep.notes.append("no ruled tables found; returned text lines (may need review)")
        df = pd.DataFrame({"text": lines})
        rep.rows, rep.cols = len(df), len(df.columns)
        return df, rep
    # stack tables that share the same width; use the first row as header
    big = max(tables, key=len)
    header = [str(c).strip() or f"column_{j+1}_no_header" for j, c in enumerate(big[0])]
    body = []
    for t in tables:
        if len(t[0]) == len(header):
            body += [ (list(map(lambda x: "" if x is None else str(x), r)) + [""] * len(header))[:len(header)] for r in t[1:] ]
    df = pd.DataFrame(body, columns=_dedupe_headers(header))
    rep.rows, rep.cols = len(df), len(df.columns)
    if len(tables) > 1:
        rep.notes.append(f"merged {len(tables)} tables across {npages} page(s)")
    return df, rep


def _fix_serial_header(h: str) -> str:
    """A bare numeric header in the Excel date-serial range is almost always a
    date that leaked in as a number (e.g. 44562 -> 2021-12-01). Convert it."""
    import re as _r, datetime as _d
    m = _r.fullmatch(r"\d{5}(?:\.\d+)?", h)
    if m:
        f = float(h)
        if 36526 <= f <= 55153:            # 2000-01-01 .. 2051, a safe date window
            return (_d.date(1899, 12, 30) + _d.timedelta(days=int(f))).isoformat()
    return h


def _dedupe_headers(header: list[str]) -> list[str]:
    _zw = str.maketrans("", "", "\ufeff\u200b\u200c\u200d\u2060")
    seen, out = {}, []
    for j, h in enumerate(header):
        h = str(h).translate(_zw).replace("\xa0", " ").strip()   # drop BOM/zero-width, trim
        h = _fix_serial_header(h)                                # leaked Excel date serial -> ISO date
        if not h or h.lower().startswith("unnamed"):
            h = f"column_{j+1}_no_header"                        # blank header -> visible, flaggable
        if h in seen:
            seen[h] += 1
            out.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            out.append(h)
    return out


def read_any(path: str | Path) -> tuple[pd.DataFrame, IngestReport]:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in {".csv"}:      return read_csv_like(p, "csv")
    if ext in {".tsv", ".tab"}: return read_csv_like(p, "tsv")
    if ext in {".txt"}:      return read_csv_like(p, "csv")
    if ext in {".xlsx", ".xls", ".xlsm"}: return read_excel(p)
    if ext in {".json"}:     return read_json(p)
    if ext in {".pdf"}:      return read_pdf(p)
    raise ValueError(f"Unsupported file type: {ext}")

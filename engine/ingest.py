"""Robust ingestion - read messy inputs of many kinds into a clean DataFrame.

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
    is_form: bool = False

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


def _row_width(row) -> int:
    """How 'header-like' a row is. Normally the count of non-empty cells, but a
    single value smeared across many cells (a merged title banner) collapses to 1
    - so a banner never out-scores a real header, yet a genuine header with a
    repeated group label ('Score','Score') keeps its full width."""
    vals = [str(c).strip() for c in row if str(c).strip()]
    if not vals:
        return 0
    if len(set(vals)) == 1 and len(vals) > 2:
        return 1
    return len(vals)


def _is_subheader_row(row) -> bool:
    """A secondary header row (e.g. 'Term1, Term2' under merged 'Score'): a couple
    of short, mostly non-numeric labels - not a data row, not a 1-cell divider."""
    vals = [str(c).strip() for c in row if str(c).strip()]
    if len(vals) < 2:
        return False
    numeric = sum(1 for v in vals if _looks_numeric(v))
    return numeric <= len(vals) * 0.3 and all(len(v) <= 24 for v in vals)


def _header_band(rows: list[list[str]], data_start: int) -> tuple[int, int]:
    """Locate the real header block above the first data row. Anchors on the row
    with the most labels (ignoring smeared banners), extends UP to stacked header
    rows and DOWN to sub-header rows that sit between it and the data, while
    skipping blank separators and 1-cell section dividers."""
    data_ne = _row_width(rows[data_start]) if data_start < len(rows) else 1
    floor = max(3, data_ne * 0.5)
    lo = max(0, data_start - 10)
    widths = [(_row_width(rows[j]), j) for j in range(lo, data_start)]
    cands = [(w, j) for w, j in widths if w >= floor]
    if not cands:                                            # fall back to the widest non-banner row
        cands = [(w, j) for w, j in widths if w >= 2]
    if not cands:
        return max(0, data_start - 1), max(0, data_start - 1)
    best_w = max(w for w, _ in cands)
    header_j = max(j for w, j in cands if w == best_w)
    start = end = header_j
    j = header_j - 1                                         # stacked header rows ABOVE
    while j >= lo and _row_width(rows[j]) >= floor:
        start = j; j -= 1
    # sub-header rows BELOW only make sense under a spanning parent header: one
    # with gaps or a repeated group label ('Score','Score'). A complete row of
    # distinct labels has nothing to span, so the rows under it are DATA. Without
    # this, an all-text first data row ('Aisha Bello, Kano, fifty thousand') was
    # glued onto the header ('Full Name - Aisha Bello').
    anchor = [str(c).strip() for c in rows[header_j]]
    ne_anchor = [c for c in anchor if c]
    last = max((i for i, c in enumerate(anchor) if c), default=-1)
    has_span = (len(set(ne_anchor)) < len(ne_anchor)) or any(not anchor[i] for i in range(0, last + 1)) \
        or (data_start < len(rows) and len([c for c in rows[data_start] if str(c).strip()]) > len(ne_anchor))
    k = header_j + 1                                         # sub-header rows BELOW, up to the data
    while has_span and k < data_start and _is_subheader_row(rows[k]):
        end = k; k += 1
    if end - start + 1 > 3:
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
    s = s.replace(",", "").replace("%", "").replace("$", "").replace("\u20a6", "").strip()
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
            # Data starts right under the header block. The "first data row"
            # detector needs a number in the row, so an all-text first record
            # (e.g. a blank amount) would otherwise be silently dropped.
            first = min(end + 1, data_start)
            return _compose_multi(levels, forward_fill=forward_fill), first
    return [re.sub(r"\s+", " ", str(rows[hdr][j] if j < len(rows[hdr]) else "").replace("\n", " ")).strip()
            for j in range(len(rows[hdr]))], hdr + 1


import re as _re_ing
_MONTHS_ING = {"jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"}
def _is_year_header(c):
    return bool(_re_ing.fullmatch(r"(19|20)\d{2}", str(c).strip()))
def _is_month_header(c):
    return str(c).strip().lower()[:3] in _MONTHS_ING
def _is_quarter_header(c):
    return bool(_re_ing.fullmatch(r"(q[1-4])|((19|20)\d{2}[ _-]?q[1-4])", str(c).strip().lower()))
def _seq_header(c):
    """Any time-axis header (year/month/quarter) that a repeating value block hangs off."""
    return _is_year_header(c) or _is_quarter_header(c) or _is_month_header(c)


def _fill_group_labels(df: pd.DataFrame, notes: list) -> pd.DataFrame:
    """Grouped exports repeat a label (Country, Region) only on the first or last
    row of each group and leave the rest blank. For a LEADING text column that is
    sparsely filled (a label, not data), fill the gaps so every row carries its
    group. Conservative: only the leading id-like columns, only when clearly sparse,
    and tries forward-fill then back-fill so either 'label-on-top' or 'label-on-
    summary-row' layouts populate."""
    cols = list(df.columns)
    # Only fill group labels when this genuinely looks like a grouped PANEL table:
    # there must be a run of time-axis (year/quarter/month) columns. Otherwise a
    # form/edge file (sparse first column of one-off labels like "Sub-Total") would
    # be wrongly filled and corrupted. This keeps the fill to the case it's for.
    has_axis = sum(1 for c in cols if _seq_header(c)) >= 5
    if not has_axis:
        return df
    filled = 0
    for c in cols[:2]:                        # only the leading id/label columns
        if _seq_header(c):
            break
        s = df[c].astype(str).str.strip().replace("nan", "").replace("", pd.NA)
        nonblank = s.notna().mean()
        if 0 < nonblank < 0.6:                # sparse label alongside a time axis -> a group key
            ff = s.ffill(); bf = s.bfill()
            df[c] = (ff.where(ff.notna(), bf)).fillna("")
            filled += 1
        else:
            break
    if filled:
        notes.append(f"filled group labels in {filled} column(s)")
    return df


def _pair_year_value_columns(df: pd.DataFrame, notes: list) -> pd.DataFrame:
    """Repeating time-axis groups (OECD/Eurostat/WDI and similar): a time header
    (year, quarter, or month) whose own column is empty because the VALUE lives in
    the blank column right after it (a 'flag column' layout). Detect the pattern for
    ANY time axis and move each value under its header, dropping the empty flags.
    General and conservative: only fires when the axis column is mostly empty and its
    blank-header right neighbour holds the data, so normal tables and clean panels
    (where the axis columns already hold values) are never touched."""
    cols = list(df.columns)
    def _empty_share(s):
        v = s.astype(str).str.strip().replace("nan", "")
        return (v == "").mean() if len(v) else 1.0
    def _blank_header(c):
        s = str(c).strip()
        return s == "" or s.lower().startswith("unnamed") or "no_header" in s.lower()
    moved = 0; drop_idx = set()
    for i, c in enumerate(cols):
        if not _seq_header(c):               # any time axis, not just years
            continue
        if i + 1 >= len(cols):
            continue
        nxt = cols[i + 1]
        if not _blank_header(nxt):
            continue
        if _empty_share(df[c]) >= 0.8 and _empty_share(df[nxt]) < 0.8:
            df[c] = df[nxt].values           # value under the time header
            drop_idx.add(i + 1)
            moved += 1
    if moved:
        keep = [c for j, c in enumerate(cols) if j not in drop_idx]
        df = df[keep]
        notes.append(f"paired {moved} time column(s) with their value column")
    return df


def _drop_empty_columns(df: pd.DataFrame, notes: list) -> pd.DataFrame:
    """Remove columns that hold no data at all (blank spacer columns common in
    spreadsheet exports). Reported, never silent. Never drops a YEAR-headed column
    though: in panel exports (OECD/Eurostat) early years can be all-missing, and
    dropping them would silently delete part of the time axis."""
    keep = [c for c in df.columns
            if _is_year_header(c) or df[c].astype(str).str.strip().replace("nan", "").ne("").any()]
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
        if col0_distinct > 0.8 and _types_run_across_rows(body):
            return "transposed"
    return "normal"


def _types_run_across_rows(body) -> bool:
    """In a normal table each COLUMN holds one kind of value (all numbers, or all
    text). In a transposed one each ROW does. Only call it transposed when rows
    are clearly more uniform than columns, so a short, wide table is never
    flipped on its side just because it has few records."""
    grid = [[str(c).strip() for c in r[1:]] for r in body]
    width = max((len(r) for r in grid), default=0)
    if width < 2 or len(grid) < 2:
        return False
    def uniform(cells):
        v = [c for c in cells if c]
        if len(v) < 2:
            return None
        k = sum(1 for c in v if _looks_numeric(c))
        return max(k, len(v) - k) / len(v)
    cols = [uniform([r[j] if j < len(r) else "" for r in grid]) for j in range(width)]
    rows_ = [uniform(r) for r in grid]
    cols = [x for x in cols if x is not None]; rows_ = [x for x in rows_ if x is not None]
    if not cols or not rows_:
        return False
    return (sum(rows_) / len(rows_)) > (sum(cols) / len(cols)) + 0.15


def _maybe_form(rows):
    """If the raw rows are a FORM/layout (not a data table), return a tidy 2-column
    dataframe of the extracted field->value pairs; else None."""
    try:
        from engine.structure import detect_form
        f = detect_form(pd.DataFrame(rows))
        if f.get("is_form") and f.get("label_values"):
            return pd.DataFrame(f["label_values"], columns=["field", "value"])
    except Exception:
        pass
    return None


def _form_report(path, kind, sheet=None):
    rep = IngestReport(str(path), kind, sheet=sheet)
    rep.is_form = True
    rep.notes.append("this sheet looks like a form (label:value layout), not a data table; extracted the fields")
    return rep


def _find_year_header_row(rows: list[list[str]], scan: int = 25) -> int:
    """Panel/time-series files (OECD, Eurostat, WDI) have a header row that is a
    few TEXT labels (Country, Sex) followed by a run of YEAR columns (1960, 1961…),
    often with blank flag columns between them. The generic header detector scores
    such a row LOW because most of its cells are numeric. Find it directly: the row
    with the longest run of year-like tokens (>=5) wins; everything above it is
    metadata/XML preamble to skip."""
    best_i, best_n = -1, 0
    for i, row in enumerate(rows[:scan]):
        cells = [str(c).strip() for c in row]
        n = sum(1 for c in cells if _seq_header(c))   # years, quarters, or months
        if n >= 5 and n > best_n:
            best_n, best_i = n, i
    return best_i


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
    _fdf = _maybe_form(rows)
    if _fdf is not None:
        _r=_form_report(path, kind); _r.rows=len(_fdf); _r.cols=2; return _fdf, _r   # a form, not a table
    # Panel/time-series files: a year-header row after a metadata/XML preamble.
    # Detect it directly (the generic detector under-scores numeric year headers).
    _yhr = _find_year_header_row(rows)
    if _yhr >= 0:
        header = [str(c).strip() for c in rows[_yhr]]
        data_start = _yhr + 1
    else:
        hdr = _detect_header_row([r for r in rows if any(str(c).strip() for c in r)])
        header, data_start = _resolve_header(rows, hdr)      # multi-row header on CSV too
    header = [str(c).strip() or f"column_{j+1}_no_header" for j, c in enumerate(header)]
    orient = detect_orientation([r for r in rows[data_start:data_start + 200] if any(str(c).strip() for c in r)])
    width = len(header)
    body_rows = [r for r in rows[data_start:] if any(str(c).strip() for c in r)]
    if width >= 4:                                           # wide table: 1-cell rows are dividers
        body_rows = [r for r in body_rows if sum(1 for c in r if str(c).strip()) > 1]
    body = [(r + [""] * width)[:width] for r in body_rows]
    df = pd.DataFrame(body, columns=_dedupe_headers(header))
    if orient == "transposed":
        df = _transpose(df)
    _empty_notes = []
    df = _pair_year_value_columns(df, _empty_notes)   # OECD/Eurostat: value sits beside the year header
    df = _fill_group_labels(df, _empty_notes)         # grouped exports: fill sparse leading label columns
    df = _drop_empty_columns(df, _empty_notes)        # remove blank spacer columns
    rep = IngestReport(str(path), kind, encoding=enc, delimiter=delim, header_row=data_start,
                       rows=len(df), cols=len(df.columns))
    for _n in _empty_notes:
        rep.notes.append(_n)
    rep.notes.append(f"layout detected: {orient}")
    if data_start > 0:
        rep.skipped_rows = [" · ".join(c.strip() for c in rows[k] if c.strip()) for k in range(max(0, data_start - 1))]
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


_HELPER_SHEET = re.compile(r"\b(check|notes?|readme|meta(data)?|temp|tmp|qa|pivot|lookup|drop.?down|list|ref|scratch|working|calc|copy|backup|old|archive|bak|test|draft|deprecated)\b|\(\s*\d+\s*\)|\bv?\d+\b\s*$", re.I)


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
    _fdf = _maybe_form(raw)
    if _fdf is not None:
        _r=_form_report(path, 'xlsx', sheet=sheet); _r.rows=len(_fdf); _r.cols=2; return _fdf, _r   # a form, not a table
    raw = [r for r in raw if any(str(c).strip() for c in r)]
    if not raw:
        raise ValueError(f"The sheet {sheet!r} is empty. Pick a sheet that has data.")
    hdr = _detect_header_row([[str(c) for c in r] for r in raw])
    header, data_start = _resolve_header(raw, hdr, forward_fill=(not merged))
    header = [str(c).strip() or f"column_{j+1}_no_header" for j, c in enumerate(header)]
    width = len(header)
    body_rows = raw[data_start:]
    dividers = 0
    if width >= 4:                                              # wide table: 1-cell rows are dividers
        kept = []
        for r in body_rows:
            if sum(1 for c in r if str(c).strip()) <= 1 and any(str(c).strip() for c in r):
                dividers += 1                                   # e.g. ">>> LAGOS STATE <<<"
            else:
                kept.append(r)
        body_rows = kept
    body = [(list(map(str, r)) + [""] * width)[:width] for r in body_rows]
    df = pd.DataFrame(body, columns=_dedupe_headers(header))
    rep_notes = []
    # same layout repairs as CSV: a country/region written once and left blank
    # for the rows under it ('Australia', '', '') is filled down, so those rows
    # are never mistaken for repeats of another country's rows
    df = _pair_year_value_columns(df, rep_notes)
    df = _fill_group_labels(df, rep_notes)
    df = _drop_empty_columns(df, rep_notes)
    if dividers:
        rep_notes.append(f"removed {dividers} section-divider/label row(s) from the data")
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
            grid = grids[s]
            data_rows = sum(1 for r in grid if sum(1 for c in r if str(c).strip()) >= 2)
            if data_rows == 0:
                return -1.0
            name_penalty = 0.5 if _HELPER_SHEET.search(s) else 1.0
            # prefer the sheet with the most actual data; density is only a tie-break,
            # so a tiny clean junk sheet never beats the large real table.
            import math
            return (math.log1p(data_rows) + 0.3 * _sheet_density(grid)) * name_penalty
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
        # no ruled tables - fall back to whitespace-delimited text lines
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


def list_sheets(path: Path) -> list[dict]:
    """List a workbook's sheets with a data-size estimate and a 'likely real data'
    flag, so the UI can let the user pick which sheet(s) to clean."""
    ext = Path(path).suffix.lower()
    if ext not in {".xlsx", ".xls", ".xlsm"}:
        return []
    xl = pd.ExcelFile(path)
    out = []
    best_score = -1.0; best = None
    import math
    for s in xl.sheet_names:
        grid = xl.parse(s, header=None, dtype=str).fillna("").values.tolist()
        data_rows = sum(1 for r in grid if sum(1 for c in r if str(c).strip()) >= 2)
        cols = max((sum(1 for c in r if str(c).strip()) for r in grid), default=0)
        helper = bool(_HELPER_SHEET.search(s))
        score = (math.log1p(data_rows) + 0.3 * _sheet_density(grid)) * (0.5 if helper else 1.0)
        if score > best_score: best_score = score; best = s
        # first row with 2+ cells is (usually) the header: show a few column names
        # so people recognise the sheet without opening Excel
        head = next((r for r in grid if sum(1 for c in r if str(c).strip()) >= 2), [])
        preview = [str(c).strip() for c in head if str(c).strip()][:5]
        out.append({"name": s, "rows": max(0, data_rows - 1), "cols": cols, "helper": helper,
                    "empty": data_rows < 2, "columns_preview": preview})
    for r in out:
        r["recommended"] = (r["name"] == best and not r["empty"])
    return out


def read_any(path: str | Path, sheet: str | None = None) -> tuple[pd.DataFrame, IngestReport]:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in {".csv"}:      return read_csv_like(p, "csv")
    if ext in {".tsv", ".tab"}: return read_csv_like(p, "tsv")
    if ext in {".txt"}:      return read_csv_like(p, "csv")
    if ext in {".xlsx", ".xls", ".xlsm"}: return read_excel(p, sheet=sheet)
    if ext in {".json"}:     return read_json(p)
    if ext in {".pdf"}:      return read_pdf(p)
    raise ValueError(f"Unsupported file type: {ext}")

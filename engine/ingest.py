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
    try:
        from charset_normalizer import from_bytes
        m = from_bytes(raw).best()
        if m is not None:
            return m.encoding
    except Exception:
        pass
    return "utf-8"


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


def _detect_header_row(rows: list[list[str]]) -> int:
    """Find the first row that looks like a header: mostly non-empty, mostly
    non-numeric, and followed by a row of similar width."""
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


# ---------------------------------------------------------------------------
def read_csv_like(path: Path, kind: str) -> tuple[pd.DataFrame, IngestReport]:
    raw = path.read_bytes()
    enc = _sniff_encoding(raw)
    text = raw.decode(enc, errors="replace")
    delim = "\t" if kind == "tsv" else _sniff_delimiter(text)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    rows = [r for r in rows if any(c.strip() for c in r)]  # drop blank lines
    hdr = _detect_header_row(rows)
    header = [c.strip() or f"col_{j+1}" for j, c in enumerate(rows[hdr])]
    body = rows[hdr + 1:]
    width = len(header)
    body = [(r + [""] * width)[:width] for r in body]  # pad/trim ragged rows
    df = pd.DataFrame(body, columns=_dedupe_headers(header))
    rep = IngestReport(str(path), kind, encoding=enc, delimiter=delim, header_row=hdr + 1,
                       rows=len(df), cols=len(df.columns))
    if hdr > 0:
        rep.notes.append(f"skipped {hdr} banner/metadata row(s) above the header")
        rep.skipped_rows = [" · ".join(c.strip() for c in rows[k] if c.strip()) for k in range(hdr)]
    return df, rep


def read_excel(path: Path) -> tuple[pd.DataFrame, IngestReport]:
    xl = pd.ExcelFile(path)
    sheets = xl.sheet_names
    # choose the sheet with the most non-empty cells
    best, best_cells = sheets[0], -1
    for s in sheets:
        raw = xl.parse(s, header=None, dtype=str)
        cells = raw.notna().sum().sum()
        if cells > best_cells:
            best, best_cells = s, cells
    raw = xl.parse(best, header=None, dtype=str).fillna("").values.tolist()
    raw = [r for r in raw if any(str(c).strip() for c in r)]
    hdr = _detect_header_row([[str(c) for c in r] for r in raw])
    header = [str(c).strip() or f"col_{j+1}" for j, c in enumerate(raw[hdr])]
    body = [ (list(map(str, r)) + [""] * len(header))[:len(header)] for r in raw[hdr + 1:] ]
    df = pd.DataFrame(body, columns=_dedupe_headers(header))
    rep = IngestReport(str(path), "xlsx", sheet=best, sheets_found=sheets,
                       header_row=hdr + 1, rows=len(df), cols=len(df.columns))
    if len(sheets) > 1:
        rep.notes.append(f"{len(sheets)} sheets; picked the fullest ({best!r})")
    if hdr > 0:
        rep.notes.append(f"skipped {hdr} banner/metadata row(s) above the header")
        rep.skipped_rows = [" · ".join(str(c).strip() for c in raw[k] if str(c).strip()) for k in range(hdr)]
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
    header = [str(c).strip() or f"col_{j+1}" for j, c in enumerate(big[0])]
    body = []
    for t in tables:
        if len(t[0]) == len(header):
            body += [ (list(map(lambda x: "" if x is None else str(x), r)) + [""] * len(header))[:len(header)] for r in t[1:] ]
    df = pd.DataFrame(body, columns=_dedupe_headers(header))
    rep.rows, rep.cols = len(df), len(df.columns)
    if len(tables) > 1:
        rep.notes.append(f"merged {len(tables)} tables across {npages} page(s)")
    return df, rep


def _dedupe_headers(header: list[str]) -> list[str]:
    seen, out = {}, []
    for h in header:
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

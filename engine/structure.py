"""Whole-table structure detection: spot wide/panel data (a run of year/month/
quarter columns) so we can offer to reshape to long format.

Conservative by design: only reports panel_wide on a clear, single-measure panel
(>= 5 sequence headers, mostly numeric, with at least one id column to the left).
Everything else is 'flat' and behaviour is unchanged.
"""
from __future__ import annotations

import re

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _is_year(h):
    s = str(h).strip()
    return bool(re.fullmatch(r"(19|20)\d{2}", s))


def _is_month(h):
    s = str(h).strip().lower()[:3]
    return s in _MONTHS


def _is_quarter(h):
    s = str(h).strip().lower()
    return bool(re.fullmatch(r"(q[1-4])|((19|20)\d{2}[ _-]?q[1-4])", s))


def _seq_kind(headers):
    """Return the axis kind if most headers form a year/month/quarter sequence."""
    hs = [str(h).strip() for h in headers]
    if not hs:
        return None
    for name, test in (("year", _is_year), ("quarter", _is_quarter), ("month", _is_month)):
        hits = sum(1 for h in hs if test(h))
        if hits >= max(5, int(0.6 * len(hs))):
            return name
    return None


_NULLISH = {"", "-", "--", "..", "...", "n/a", "na", "nan", "none", "null", "nil", "#n/a", ".."}


def _looks_number(v):
    """Tolerant numeric test: strips %, currency, thousands separators, spaces,
    footnote marks and parentheses-negatives, so real-world measure cells count."""
    s = str(v).strip()
    if s.lower() in _NULLISH:
        return None  # neutral: doesn't count for or against
    t = s.replace(",", "").replace("\u00a0", "").replace(" ", "")
    t = t.strip("%")
    t = re.sub(r"^[₦$€£]", "", t)
    t = re.sub(r"[*\u2020\u2021a-eA-E]$", "", t)      # trailing footnote marks
    if t.startswith("(") and t.endswith(")"):
        t = "-" + t[1:-1]                              # (123) accounting negative
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", t))


def _mostly_numeric(df, cols, sample=300):
    """A column block is a numeric measure if, among its NON-empty cells, most look
    numeric, and sparse/empty columns don't count against it (panels are sparse)."""
    ok = 0; considered = 0
    for c in cols:
        vals = [v for v in df[c].dropna().tolist()[:sample]]
        judged = [(_looks_number(v)) for v in vals]
        judged = [j for j in judged if j is not None]   # drop null-ish cells
        if not judged:
            ok += 1  # all-empty/sparse column: neutral, treat as compatible
            continue
        considered += 1
        if sum(1 for j in judged if j) / len(judged) >= 0.6:
            ok += 1
    # need at least a few genuinely-numeric columns, and most compatible overall
    return bool(cols) and considered >= 3 and ok / len(cols) >= 0.6


def detect_form(df) -> dict:
    """Decide whether a sheet is a real DATA TABLE or a FORM/layout (a printable
    template: a title, label:value pairs, embedded mini-tables, signature lines) that
    has no consistent record grid. Forms should not be tabulated like data. Signals:
    very sparse cells, most non-empty text sitting in one column, many 'Label:' cells,
    and few rows that look like full records. Returns {is_form, label_values} where
    label_values is the extracted [{field, value}] pairs when it is a form."""
    import re as _re
    rows = df.astype(str).replace("nan", "").values.tolist()
    n = len(rows); ncol = len(df.columns) if n else 0
    if n == 0 or ncol == 0:
        return {"is_form": False, "label_values": []}
    def cells(r): return [c for c in r if str(c).strip()]
    nonempty_per_row = [len(cells(r)) for r in rows]
    filled_rows = [k for k in nonempty_per_row if k >= max(2, int(0.5 * ncol))]
    density = sum(nonempty_per_row) / (n * ncol)
    # 'record-like' rows: at least half the columns filled
    record_share = (len(filled_rows) / n) if n else 0
    # label:value cells (end with ':' or a lone label in an otherwise empty row)
    label_cells = 0; lv = []
    for r in rows:
        cs = [(j, str(c).strip()) for j, c in enumerate(r) if str(c).strip()]
        if 1 <= len(cs) <= 3:
            for j, c in cs:
                if c.endswith(":") or _re.search(r":\s*$", c):
                    label = c.rstrip(": ").strip()
                    val = ""
                    after = [v for (jj, v) in cs if jj > j and v]
                    if after: val = after[0]
                    if label: lv.append({"field": label, "value": val}); label_cells += 1
    # A form: sparse, few full-record rows, and several label cells.
    is_form = (density < 0.35 and record_share < 0.25 and label_cells >= 4)
    return {"is_form": bool(is_form), "label_values": lv[:60]}


def detect_structure(df) -> dict:
    """Look at the whole table and decide if it's a wide/panel shape."""
    flat = {"kind": "flat", "id_cols": [], "value_cols": [], "axis_name": "period",
            "n_periods": 0, "confidence": 0.0}
    cols = list(df.columns)
    if len(cols) < 6:
        return flat

    # find the longest contiguous run of sequence-like headers
    def classify(h):
        if _is_year(h): return "year"
        if _is_quarter(h): return "quarter"
        if _is_month(h): return "month"
        return None

    # Collect ALL sequence-like columns (years/quarters/months), even when they are
    # interleaved with blank "flag" columns (OECD/Eurostat put an empty flag column
    # after each year). We don't require a contiguous run — we gather every year
    # column and treat the rest as id/flag columns.
    def _blankish(c):
        s = str(c).strip()
        return s == "" or s.lower().startswith("unnamed") or "no_header" in s.lower()

    seq = [(c, classify(c)) for c in cols if classify(c)]
    if not seq:
        return flat
    # dominant axis kind among the sequence columns
    from collections import Counter as _C
    kind = _C(k for _, k in seq).most_common(1)[0][0]
    value_cols = [c for c, k in seq if k == kind]
    if len(value_cols) < 5:
        return flat
    if not _mostly_numeric(df, value_cols):
        return flat

    vc = set(value_cols)
    id_cols = [c for c in cols if c not in vc and not _blankish(c)]   # real ids only, not flag columns
    if len(id_cols) < 1:
        return flat
    # id columns should be to the LEFT (typical panel); allow a few trailing.
    conf = min(0.95, 0.5 + 0.05 * len(value_cols))
    return {"kind": "panel_wide", "id_cols": id_cols, "value_cols": value_cols,
            "axis_name": kind, "n_periods": len(value_cols), "confidence": round(conf, 2)}

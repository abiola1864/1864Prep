"""Reshaping operations from the common cleaning tasks: split one column into
several, merge several into one, and extract date parts. These change the table
shape, so they're offered as explicit actions (worklist), not silent transforms.

All deterministic; they return new columns without touching the originals until
the person applies them.
"""
from __future__ import annotations

import re

import pandas as pd

_WS = re.compile(r"\s+")


def _s(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return _WS.sub(" ", str(v).strip())


def split_by_delimiter(series: pd.Series, delimiter: str = ",", maxsplit: int = 1,
                       names: list[str] | None = None) -> pd.DataFrame:
    """'Lagos, Nigeria' -> two columns. Splits on the first `maxsplit` delimiters."""
    parts = series.map(_s).str.split(re.escape(delimiter), n=maxsplit, expand=True)
    parts = parts.apply(lambda col: col.map(lambda x: _s(x)))
    cols = names or [f"{series.name}_{i+1}" for i in range(parts.shape[1])]
    parts.columns = cols[:parts.shape[1]]
    return parts


def split_name(series: pd.Series, order: str = "first_last") -> pd.DataFrame:
    """'ADEYEMI, Tunde' or 'Tunde Adeyemi' -> first / surname columns.
    order: 'first_last' (default) or 'last_first' for 'Surname, First' inputs."""
    first, last = [], []
    for v in series.map(_s):
        if "," in v:                                   # 'Surname, First'
            a, b = [p.strip() for p in v.split(",", 1)]
            f, l = (b, a)
        else:
            toks = v.split()
            if not toks:
                f = l = ""
            elif order == "last_first":
                l, f = toks[0], " ".join(toks[1:])
            else:
                f, l = toks[0], " ".join(toks[1:])
        first.append(f.title() if f else "")
        last.append(l.title() if l else "")
    return pd.DataFrame({f"{series.name}_first": first, f"{series.name}_surname": last})


def split_number_text(series: pd.Series) -> pd.DataFrame:
    """'Musa 34' -> text 'Musa', number '34'. Pulls a trailing/leading number out."""
    texts, nums = [], []
    for v in series.map(_s):
        m = re.search(r"[-+]?\d[\d,\.]*", v)
        if m:
            nums.append(m.group(0).replace(",", ""))
            texts.append(_s(v[:m.start()] + " " + v[m.end():]))
        else:
            nums.append("")
            texts.append(v)
    return pd.DataFrame({f"{series.name}_text": texts, f"{series.name}_number": nums})


def merge_columns(df: pd.DataFrame, columns: list[str], sep: str = " ",
                  name: str | None = None) -> pd.Series:
    """Concatenate several columns into one (skipping blanks)."""
    def row(r):
        return sep.join([_s(r[c]) for c in columns if _s(r[c])])
    out = df.apply(row, axis=1)
    out.name = name or "_".join(columns)
    return out


def date_part(series: pd.Series, part: str = "year") -> pd.Series:
    """Extract 'year' or 'month' from a date-ish column (via dateparser)."""
    import dateparser
    def one(v):
        v = _s(v)
        if not v:
            return ""
        d = dateparser.parse(v)
        if d is None:
            return ""
        return str(d.year) if part == "year" else f"{d.month:02d}"
    out = series.map(one)
    out.name = f"{series.name}_{part}"
    return out


def split_geopoint(series: pd.Series) -> pd.DataFrame:
    """'6.45, 3.39' / '(6.45; 3.39)' / '6.45 3.39' -> latitude, longitude decimals."""
    import re as _re
    try:
        from lat_lon_parser import parse
    except Exception:
        parse = None
    lats, lons = [], []
    for v in series.map(_s):
        parts = [p for p in _re.split(r"[;,]|\s+", v.strip("()[] ")) if p]
        # recombine tokens if DMS produced >2 pieces: take first half / second half
        if len(parts) == 2:
            a, b = parts
        elif len(parts) > 2:
            mid = len(parts) // 2
            a, b = " ".join(parts[:mid]), " ".join(parts[mid:])
        else:
            lats.append(""); lons.append(""); continue
        def dec(x):
            if parse is None:
                try: return str(float(x))
                except ValueError: return ""
            try: return str(round(float(parse(x)), 6))
            except Exception: return ""
        lats.append(dec(a)); lons.append(dec(b))
    return pd.DataFrame({f"{series.name}_lat": lats, f"{series.name}_long": lons})

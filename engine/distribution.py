"""Distribution insight — the 'wow' before value cleaning and after.

Gives the interface everything it needs to show a person the shape of their data:
a histogram, the mean/median, and flagged outliers, for each column that a
distribution makes sense for. It works on BOTH the raw (messy) data and the
cleaned data, so the interface can show a before/after reveal:

  * BEFORE ("this is what you had before we cooked"): we only include columns that
    are *mostly numeric even while stored as text*, because a distribution of raw
    text is meaningless. We report how much was unparseable, which is itself the
    story ("18% of this column could not be read as a number").
  * AFTER: the same columns, now clean, with tidy bins, mean/median, and outliers.

Pure computation, no plotting library: returns bins and numbers the UI draws.
"""
from __future__ import annotations

import re

import pandas as pd

_STRIP = re.compile(r"[,\s%$₦£€]")


def _to_numbers(series) -> tuple[pd.Series, float]:
    """Coerce a column to numbers; return (values, share_parseable)."""
    s = series.astype(str).str.strip()
    non_empty = s[s.ne("") & s.str.lower().ne("nan")]
    if non_empty.empty:
        return pd.Series(dtype=float), 0.0
    nums = pd.to_numeric(non_empty.str.replace(_STRIP, "", regex=True), errors="coerce")
    share = float(nums.notna().mean())
    return nums.dropna(), share


def _histogram(vals: pd.Series, bins: int = 12) -> list[dict]:
    if vals.empty:
        return []
    lo, hi = float(vals.min()), float(vals.max())
    if lo == hi:
        return [{"lo": lo, "hi": hi, "count": int(len(vals))}]
    width = (hi - lo) / bins
    out = []
    for b in range(bins):
        left = lo + b * width
        right = hi if b == bins - 1 else left + width
        in_bin = vals[(vals >= left) & (vals <= right)] if b == bins - 1 else vals[(vals >= left) & (vals < right)]
        out.append({"lo": round(left, 3), "hi": round(right, 3), "count": int(len(in_bin))})
    return out


def _stats(vals: pd.Series) -> dict:
    q1, q3 = float(vals.quantile(0.25)), float(vals.quantile(0.75))
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = vals[(vals < lo) | (vals > hi)]
    return {
        "count": int(len(vals)),
        "mean": round(float(vals.mean()), 3),
        "median": round(float(vals.median()), 3),
        "min": round(float(vals.min()), 3),
        "max": round(float(vals.max()), 3),
        "q1": round(q1, 3), "q3": round(q3, 3),
        "outlier_low": round(lo, 3), "outlier_high": round(hi, 3),
        "outliers": int(len(outliers)),
        "skew": round(float(vals.skew()), 2) if len(vals) > 2 else 0.0,
    }


def _category_profile(series, col, top_n=8) -> dict:
    """Top values + completeness for a genuine low-cardinality category. Identifier
    and phone columns are handled elsewhere (see _looks_identifier), so this stays
    focused on categories worth charting."""
    s = series.astype(str).str.strip()
    non_empty = s[s.ne("") & s.str.lower().ne("nan") & s.ne("-")]
    total = len(s)
    filled = len(non_empty)
    if filled == 0:
        return {"column": str(col), "kind": "categorical", "distinct": 0,
                "filled": 0, "missing": total, "fill_share": 0.0, "top": [], "other": 0}
    vc = non_empty.value_counts()
    top = [{"value": (str(k)[:28]), "count": int(v)} for k, v in vc.head(top_n).items()]
    other = int(vc.iloc[top_n:].sum()) if len(vc) > top_n else 0
    return {
        "column": str(col), "kind": "categorical",
        "distinct": int(len(vc)), "filled": filled, "missing": total - filled,
        "fill_share": round(filled / total, 3) if total else 0.0,
        "top": top, "other": other,
    }


_STRIP = re.compile(r"[,\s%$₦£€]")
_NONDIGIT = re.compile(r"\D")
_PHONEISH = re.compile(r"^[\d\s\-\+\(\)\.]+$")


def _digits(v: str) -> str:
    return _NONDIGIT.sub("", str(v))


def _looks_identifier(non_empty) -> bool:
    """True for phone numbers, IDs, account/reference codes: long digit strings,
    leading-zero codes, or phone-punctuation — things where an average or a
    frequency chart says nothing useful."""
    vals = [str(v).strip() for v in non_empty.tolist()[:500] if str(v).strip()]
    if not vals:
        return False
    n = len(vals)
    leading_zero = sum(1 for v in vals if re.fullmatch(r"0\d{2,}", v))
    long_digit = sum(1 for v in vals if _PHONEISH.match(v) and len(_digits(v)) >= 7)
    if long_digit / n >= 0.6:
        return True
    if leading_zero / n >= 0.3:
        return True
    return False


def _identifier_profile(series, col, kind_hint="identifier") -> dict:
    """Completeness + validity for phone/ID/code columns — no average, no chart of
    unique values, because neither is meaningful. Formatting is stripped first."""
    s = series.astype(str).str.strip()
    non_empty = s[s.ne("") & s.str.lower().ne("nan") & s.ne("-")]
    total, filled = len(s), len(non_empty)
    distinct = non_empty.nunique()
    dig = non_empty.map(_digits)
    lens = dig.str.len()
    phone_like = int(((lens >= 7) & (lens <= 15)).sum())
    common_len = int(lens.mode().iloc[0]) if not lens.empty else 0
    return {
        "column": str(col), "kind": "identifier",
        "filled": filled, "missing": total - filled,
        "fill_share": round(filled / total, 3) if total else 0.0,
        "distinct": int(distinct),
        "unique_share": round(distinct / filled, 3) if filled else 0.0,
        "valid_format_share": round(phone_like / filled, 3) if filled else 0.0,
        "common_length": common_len,
        "note": "identifier / contact — analysed for completeness and format, not as a number",
    }


def distribution_profile(df: pd.DataFrame, min_numeric_share: float = 0.6,
                         max_columns: int = 8, bins: int = 12,
                         include_categorical: bool = True) -> list[dict]:
    """Chart-ready, TYPE-AWARE distribution for each column.

    - Real numbers (quantities): histogram + mean/median/outliers.
    - Phone / ID / code: completeness + format validity + distinct (no average,
      no frequency chart — those mislead for identifiers).
    - Categories: top-values frequency chart.
    - High-cardinality text (mostly unique): treated like an identifier summary.
    Formatting is stripped before any numeric reading.
    """
    out = []
    for col in df.columns:
        s = df[col].astype(str).str.strip()
        non_empty = s[s.ne("") & s.str.lower().ne("nan") & s.ne("-")]
        if len(non_empty) < 5:
            if include_categorical and len(non_empty) >= 1:
                out.append(_category_profile(df[col], col))
            if len(out) >= max_columns:
                break
            continue

        # identifiers/phones/codes first — never treat these as quantities
        if _looks_identifier(non_empty):
            out.append(_identifier_profile(df[col], col))
        else:
            vals, share = _to_numbers(df[col])
            if share >= min_numeric_share and len(vals) >= 5:
                item = {"column": str(col), "kind": "numeric", "numeric_share": round(share, 3),
                        "unreadable_share": round(1 - share, 3),
                        "histogram": _histogram(vals, bins)}
                item.update(_stats(vals))
                out.append(item)
            elif include_categorical:
                distinct = non_empty.nunique()
                # mostly-unique text is an identifier, not a category worth charting
                if distinct / len(non_empty) >= 0.85 and distinct > 30:
                    out.append(_identifier_profile(df[col], col))
                else:
                    out.append(_category_profile(df[col], col))
        if len(out) >= max_columns:
            break
    return out


def before_after(raw_df: pd.DataFrame, clean_df: pd.DataFrame,
                 max_columns: int = 6) -> dict:
    """Pair raw and cleaned distributions for the same columns, for a reveal.

    Matches columns by cleaned name where possible, else by position, so the
    interface can animate 'before → after' for each column."""
    before = {d["column"]: d for d in distribution_profile(raw_df, max_columns=max_columns * 2)}
    after = {d["column"]: d for d in distribution_profile(clean_df, max_columns=max_columns * 2)}

    pairs = []
    used_after = set()
    for i, (bcol, bd) in enumerate(before.items()):
        # try exact name, else same position among numeric columns
        acol = bcol if bcol in after else None
        if acol is None:
            after_cols = [c for c in after if c not in used_after]
            acol = after_cols[i] if i < len(after_cols) else None
        ad = after.get(acol) if acol else None
        if ad:
            used_after.add(acol)
        pairs.append({"column_before": bcol, "column_after": acol,
                      "before": bd, "after": ad,
                      "recovered": (ad["count"] - bd["count"]) if ad else 0})
        if len(pairs) >= max_columns:
            break

    headline = {
        "columns_shown": len(pairs),
        "values_recovered": sum(max(0, p["recovered"]) for p in pairs),
        "outliers_after": sum((p["after"]["outliers"] if p["after"] else 0) for p in pairs),
    }
    return {"headline": headline, "pairs": pairs}

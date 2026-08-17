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
    """A 'wow' for non-numeric columns: the top values and how often each occurs,
    plus completeness. Works for categories, codes, phones, gender, anything."""
    s = series.astype(str).str.strip()
    non_empty = s[s.ne("") & s.str.lower().ne("nan") & s.ne("-")]
    total = len(s)
    filled = len(non_empty)
    vc = non_empty.value_counts()
    top = [{"value": (str(k)[:28]), "count": int(v)} for k, v in vc.head(top_n).items()]
    other = int(vc.iloc[top_n:].sum()) if len(vc) > top_n else 0
    return {
        "column": str(col), "kind": "categorical",
        "distinct": int(vc.nunique() if hasattr(vc, "nunique") else len(vc)),
        "filled": filled, "missing": total - filled,
        "fill_share": round(filled / total, 3) if total else 0.0,
        "top": top, "other": other,
    }


def distribution_profile(df: pd.DataFrame, min_numeric_share: float = 0.6,
                         max_columns: int = 8, bins: int = 12,
                         include_categorical: bool = True) -> list[dict]:
    """Chart-ready distribution for each column.

    Numeric-ish columns get a histogram + mean/median/outliers. Everything else
    (categories, phones, codes, gender, text) gets a top-values frequency chart
    and completeness, so every column has a 'wow', not just numbers.
    """
    out = []
    for col in df.columns:
        vals, share = _to_numbers(df[col])
        if share >= min_numeric_share and len(vals) >= 5:
            item = {"column": str(col), "kind": "numeric", "numeric_share": round(share, 3),
                    "unreadable_share": round(1 - share, 3),
                    "histogram": _histogram(vals, bins)}
            item.update(_stats(vals))
            out.append(item)
        elif include_categorical:
            prof = _category_profile(df[col], col)
            if prof["filled"] >= 1 and prof["distinct"] >= 1:
                out.append(prof)
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

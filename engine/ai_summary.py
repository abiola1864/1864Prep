"""Whole-column summaries for the AI.

The AI cannot read 10,000 raw values per column (local models run out of room and
small models are poor at scanning long lists). Instead the engine reads EVERY value
and hands the AI a compact picture of the whole column: counts, the most common
values, rare values, value shapes, and how many parse as numbers or dates.

The engine's own guess is deliberately NOT included, so the AI gives an
independent second opinion.

Privacy: for a cloud model, values in sensitive columns (names, phones, IDs,
emails, addresses...) are replaced by their shape (Ada -> Xxx, 0803 -> 9999), so
only patterns and counts leave the computer. A local model sees real values.
"""
from __future__ import annotations

import re
from collections import Counter

from .ai_privacy import _mask, looks_sensitive

_MISSING = {"", "..", "...", ":", "-", "--", "na", "n/a", "n.a.", "#n/a", "nan", "null", "none", "nil"}
_NUM = re.compile(r"^[-+(]?\s*(?:ngn|n|₦|\$|£|€)?\s*\d[\d,\s]*(?:\.\d+)?\s*%?\)?$", re.I)
_DATE = re.compile(r"^(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}|\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4})$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
_PHONEISH = re.compile(r"^\+?[\d\s\-()]{7,}$")


def _shape(v: str) -> str:
    """'0803 123 4567' -> '9999 999 9999', 'Aisha Bello' -> 'Aa Aa' (runs collapsed)."""
    s = re.sub(r"[A-Z][a-z]+", "Aa", v)
    s = re.sub(r"[a-z]+", "a", s)
    s = re.sub(r"[A-Z]+", "A", s)
    s = re.sub(r"\d", "9", s)
    return s[:40]


def _looks_personal(name: str, vals: list[str]) -> bool:
    if looks_sensitive(name):
        return True
    if not vals:
        return False
    k = min(len(vals), 200)
    sub = vals[:k]
    if sum(1 for v in sub if _EMAIL.match(v)) > 0.3 * k:
        return True
    if sum(1 for v in sub if _PHONEISH.match(v) and len(re.sub(r"\D", "", v)) >= 10) > 0.3 * k:
        return True
    return False


def column_summary(series, name: str, cloud: bool = False, top: int = 30) -> dict:
    raw = ["" if v is None else str(v).strip() for v in series.tolist()]
    n = len(raw)
    vals = [v for v in raw if v.lower() not in _MISSING]
    personal = cloud and _looks_personal(name, vals)
    show = (lambda v: _mask(v)[:60]) if personal else (lambda v: v[:60])
    counts = Counter(vals)
    distinct = len(counts)
    common = counts.most_common(top)
    rare = [v for v, c in counts.items() if c == 1][:6] if distinct > top else []
    shapes = Counter(_shape(v) for v in vals).most_common(5)
    lens = sorted(len(v) for v in vals) or [0]
    words = (sum(len(v.split()) for v in vals) / len(vals)) if vals else 0
    return {
        "column": str(name),
        "rows": n,
        "blank_or_missing": n - len(vals),
        "distinct": distinct,
        "most_common": [[show(v), c] for v, c in common],
        "some_rare_values": [show(v) for v in rare],
        "value_shapes": [[s, c] for s, c in shapes],
        "length_min_median_max": [lens[0], lens[len(lens) // 2], lens[-1]],
        "avg_words": round(words, 1),
        "share_numeric": round(sum(1 for v in vals if _NUM.match(v)) / len(vals), 2) if vals else 0,
        "share_date_like": round(sum(1 for v in vals if _DATE.match(v)) / len(vals), 2) if vals else 0,
        "values_masked": bool(personal),
    }


def summarise_frame(df, columns=None, cloud: bool = False) -> list[dict]:
    cols = columns or list(df.columns)
    return [column_summary(df[c], c, cloud=cloud) for c in cols if c in df.columns]

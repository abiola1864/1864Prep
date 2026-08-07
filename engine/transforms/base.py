"""
Base classes for cleaning transforms.

Every transform takes a pandas Series (one column), returns a cleaned Series
plus a structured record of what it did: how many values changed, how many
were flagged for review, and a few before/after examples. That record is what
makes a run auditable — a reviewer can see exactly which rule touched which
values, without ever seeing the person the row belongs to.

Design intent (deterministic by construction):
    - Transforms never call a network or a model. They are pure, testable rules.
    - The AI mapping layer only chooses *which* transform runs on *which* column,
      and with *what* parameters. It never touches the values itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

_WS = re.compile(r"\s+")
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff\u2060"), None)
_UNI_SPACE = {ord(c): " " for c in "\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005"
              "\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000"}


def _clean_str(value: Any) -> str:
    """Shared helper: None/NaN -> ''; strip zero-width chars, turn non-breaking
    and other unicode spaces into normal spaces, then trim and collapse."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).translate(_ZERO_WIDTH).translate(_UNI_SPACE)
    return _WS.sub(" ", s.strip())


@dataclass
class Change:
    """One value that a transform altered or flagged."""
    row: int
    before: Any
    after: Any
    flagged: bool = False
    reason: str = ""


@dataclass
class TransformResult:
    """The cleaned column plus a full account of what happened to it."""
    series: pd.Series
    source_column: str
    target_field: str
    transform: str
    n_total: int = 0
    n_changed: int = 0
    n_flagged: int = 0
    examples: list[Change] = field(default_factory=list)
    flags: list[Change] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "source_column": self.source_column,
            "target_field": self.target_field,
            "transform": self.transform,
            "rows": self.n_total,
            "changed": self.n_changed,
            "flagged": self.n_flagged,
            "examples": [
                {"row": c.row, "before": _s(c.before), "after": _s(c.after)}
                for c in self.examples[:5]
            ],
            "flags": [
                {"row": c.row, "value": _s(c.before), "reason": c.reason}
                for c in self.flags[:50]
            ],
        }


def _s(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v)


class Transform:
    """Subclass and implement `apply_value`. The base handles bookkeeping."""

    name: str = "base"

    def __init__(self, **params):
        self.params = params

    # Override this. Return (new_value, flagged, reason).
    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        raise NotImplementedError

    def run(self, series: pd.Series, source_column: str, target_field: str) -> TransformResult:
        res = TransformResult(
            series=series.copy(),
            source_column=source_column,
            target_field=target_field,
            transform=self.name,
            n_total=len(series),
        )
        new_values = []
        for i, val in enumerate(series.tolist()):
            new_val, flagged, reason = self.apply_value(val)
            new_values.append(new_val)

            changed = _s(new_val) != _s(val)
            if changed:
                res.n_changed += 1
                if len(res.examples) < 5:
                    res.examples.append(Change(i, val, new_val))
            if flagged:
                res.n_flagged += 1
                res.flags.append(Change(i, val, new_val, flagged=True, reason=reason))

        res.series = pd.Series(new_values, index=series.index, name=target_field)
        return res

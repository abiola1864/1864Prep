"""Validation & parsing transforms drawn from the common data-cleaning tasks:

  * sentinel_na  -- treat refusal/"don't know" codes (998, 999, -99, …) as missing
  * range_check  -- flag numbers (or years) outside a plausible range
  * unit_numeric -- parse "3200g", "12 kg", "5 ha" into a number (+ unit), via pint

All are deterministic and flag-or-blank rather than guess. They propose; the
person confirms in review/worklist.
"""
from __future__ import annotations

import re
from typing import Any

from .base import Transform, _clean_str

_COMMON_SENTINELS = {"998", "999", "9999", "-99", "-999", "888", "-88", "9998"}
_TEXT_SENTINELS = {"don't know", "dont know", "refused", "no response", "not stated", "dk", "na"}


class SentinelNATransform(Transform):
    """params: codes (iterable of sentinel values). Values matching a sentinel
    become blank and are flagged ('refusal/DK code'); everything else passes."""
    name = "sentinel_na"

    def __init__(self, **params):
        super().__init__(**params)
        codes = params.get("codes")
        self._codes = {str(c).strip().lower() for c in codes} if codes else set(_COMMON_SENTINELS) | _TEXT_SENTINELS

    def apply_value(self, value: Any):
        s = _clean_str(value)
        if s == "":
            return "", False, ""
        if s.lower() in self._codes:
            return "", True, f"refusal/DK sentinel code ('{s}')"
        return s, False, ""


class RangeCheckTransform(Transform):
    """params: min, max (numeric bounds). Flags values outside the range (keeps
    them). Useful for ages, counts, years — e.g. age 0..120."""
    name = "range_check"

    def __init__(self, **params):
        super().__init__(**params)
        self._min = params.get("min")
        self._max = params.get("max")

    def apply_value(self, value: Any):
        s = _clean_str(value)
        if s == "":
            return "", False, ""
        try:
            x = float(re.sub(r"[,\s]", "", s))
        except ValueError:
            return value, True, "not a number (range check)"
        if self._min is not None and x < self._min:
            return value, True, f"below minimum {self._min}"
        if self._max is not None and x > self._max:
            return value, True, f"above maximum {self._max}"
        return value, False, ""


_UNIT_RE = re.compile(r"^\s*([-+]?\d[\d,\.]*)\s*([a-zA-Zµ°%/]+)\s*$")


class UnitNumericTransform(Transform):
    """Parse a number that carries a unit ('3200g', '12 kg', '5 ha', '2hrs').
    params: to (optional target unit to convert into, via pint). Output is the
    magnitude; the unit is recorded. Values with no number are flagged."""
    name = "unit_numeric"

    def __init__(self, **params):
        super().__init__(**params)
        self._to = params.get("to")

    def apply_value(self, value: Any):
        s = _clean_str(value)
        if s == "":
            return "", True, "empty"
        m = _UNIT_RE.match(s)
        if not m:
            # maybe it's a plain number
            try:
                x = float(re.sub(r"[,\s]", "", s))
                return (str(int(x)) if x.is_integer() else str(x)), False, ""
            except ValueError:
                return value, True, "no number found"
        num = float(m.group(1).replace(",", ""))
        unit = m.group(2)
        if self._to:
            try:
                import pint
                ureg = pint.UnitRegistry()
                converted = (num * ureg(unit)).to(self._to).magnitude
                return (str(round(converted, 4))), False, f"{num}{unit} -> {self._to}"
            except Exception:
                return str(num), True, f"could not convert '{unit}' to '{self._to}'"
        return (str(int(num)) if num.is_integer() else str(num)), False, f"unit '{unit}' removed"

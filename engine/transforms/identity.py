"""Identity-number transforms: NIN and generic fixed-length IDs."""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .base import Transform

_DIGITS = re.compile(r"\D+")


def _digits_only(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip()
    # A float like 12345678901.0 loses meaning as text; handle the ".0" tail.
    if s.endswith(".0"):
        s = s[:-2]
    return _DIGITS.sub("", s)


class NINTransform(Transform):
    """Nigerian National Identification Number: exactly 11 digits.

    Non-conforming values are kept as-is but flagged, never silently dropped —
    a bad NIN means the row cannot be matched, which is a decision for a human,
    not the cleaner.
    """
    name = "nin"

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        digits = _digits_only(value)
        if digits == "":
            return "", True, "empty NIN"
        if len(digits) != 11:
            return digits, True, f"NIN is {len(digits)} digits, expected 11"
        return digits, False, ""


class FixedLengthIdTransform(Transform):
    """Generic ID normaliser: strip non-digits, check an expected length.

    params: length (int)  -- expected digit count; 0 means don't check length.
    """
    name = "fixed_id"

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        length = int(self.params.get("length", 0))
        digits = _digits_only(value)
        if digits == "":
            return "", True, "empty id"
        if length and len(digits) != length:
            return digits, True, f"id is {len(digits)} digits, expected {length}"
        return digits, False, ""

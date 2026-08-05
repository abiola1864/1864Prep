"""Plain-text tidy-ups: names, casing, whitespace, gender codes."""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .base import Transform

_WS = re.compile(r"\s+")


def _clean_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return _WS.sub(" ", str(value).strip())


class NameTransform(Transform):
    """Trim, collapse whitespace, and title-case names (handles ALL CAPS input).

    Keeps common name particles lower-cased (de, van, bin) and fixes O'/Mc.
    """
    name = "name"
    _particles = {"de", "van", "von", "bin", "al", "el", "da", "di", "la"}

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _clean_str(value)
        if s == "":
            return "", True, "empty name"
        parts = []
        for w in s.split(" "):
            lw = w.lower()
            if lw in self._particles:
                parts.append(lw)
            elif lw.startswith("o'") and len(lw) > 2:
                parts.append("O'" + lw[2:].capitalize())
            elif lw.startswith("mc") and len(lw) > 2:
                parts.append("Mc" + lw[2:].capitalize())
            else:
                parts.append(w.capitalize())
        return " ".join(parts), False, ""


class UpperTransform(Transform):
    name = "upper"

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _clean_str(value)
        return s.upper(), False, ""


class GenderTransform(Transform):
    """Normalise assorted gender codes to M / F, flagging anything unclear."""
    name = "gender"
    _map = {
        "m": "M", "male": "M", "man": "M", "1": "M", "boy": "M",
        "f": "F", "female": "F", "woman": "F", "2": "F", "girl": "F",
    }

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _clean_str(value).lower()
        if s == "":
            return "", True, "empty gender"
        if s in self._map:
            return self._map[s], False, ""
        return value, True, "gender not recognised"


class EmailTransform(Transform):
    name = "email"
    _re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _clean_str(value).lower()
        if s == "":
            return "", True, "empty email"
        return (s, False, "") if self._re.match(s) else (s, True, "not a valid email")


class BooleanTransform(Transform):
    name = "boolean"
    _map = {"yes": "Yes", "y": "Yes", "true": "Yes", "1": "Yes",
            "no": "No", "n": "No", "false": "No", "0": "No"}

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _clean_str(value).lower()
        if s == "":
            return "", True, "empty boolean"
        return (self._map[s], False, "") if s in self._map else (value, True, "not a boolean")


class NumericTransform(Transform):
    name = "numeric"

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _clean_str(value)
        # strip common currency symbols, thousands separators, spaces, and % 
        s = re.sub(r"[,$£€₦%\s]", "", s)
        if s == "":
            return "", True, "empty numeric"
        try:
            f = float(s)
            return (str(int(f)) if f.is_integer() else str(f)), False, ""
        except ValueError:
            return value, True, "not numeric"


class TextNormaliseTransform(Transform):
    name = "text_normalise"

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        return _clean_str(value), False, ""

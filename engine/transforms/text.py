"""Plain-text tidy-ups: names, casing, whitespace, gender codes."""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .base import Transform

_WS = re.compile(r"\s+")


from .base import _clean_str  # shared helper (defined in base)


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
    """Validate + normalise emails via `email_validator` (syntax + normalised
    form), falling back to a regex if the library is unavailable. No network /
    deliverability checks — fully offline."""
    name = "email"
    _re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _clean_str(value).strip()
        if s == "":
            return "", True, "empty email"
        try:
            from email_validator import EmailNotValidError, validate_email
            info = validate_email(s, check_deliverability=False)
            return info.normalized.lower(), False, ""
        except ImportError:
            return (s.lower(), False, "") if self._re.match(s) else (s, True, "not a valid email")
        except Exception:
            return s, True, "not a valid email"


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
    """Locale/currency-robust number parsing via `price_parser` (handles ₦, $, €,
    thousands separators, comma-vs-dot decimals), plus parentheses-negatives and
    trailing %. A digit must be present, so 'free'/'N/A' are flagged, not zeroed."""
    name = "numeric"

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _clean_str(value)
        if s == "":
            return "", True, "empty numeric"
        if not any(ch.isdigit() for ch in s):
            return value, True, "not numeric (no digits)"
        neg = s.strip().startswith("(") and s.strip().endswith(")")
        pct = s.strip().endswith("%")
        try:
            from price_parser import Price
            amount = Price.fromstring(s).amount_float
        except Exception:
            amount = None
        if amount is None:
            try:
                amount = float(re.sub(r"[^\d.\-eE]", "", s.replace(",", "")))
            except ValueError:
                return value, True, "not numeric"
        if neg:
            amount = -abs(amount)
        if pct:
            note = "read as percent value"
            return (str(int(amount)) if float(amount).is_integer() else str(amount)), False, note
        return (str(int(amount)) if float(amount).is_integer() else str(amount)), False, ""


class TextNormaliseTransform(Transform):
    name = "text_normalise"

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        return _clean_str(value), False, ""


class TextCleanTransform(Transform):
    """Natural-language cleanup: repair encoding, strip invisible characters,
    normalise quotes/dashes/whitespace, and treat NA-tokens as blank."""
    name = "text_clean"

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        from ..textclean import normalize_missing, normalize_text
        cleaned = normalize_missing(value)
        raw = "" if value is None else str(value)
        if cleaned == "" and normalize_text(value) != "":
            return "", False, ""      # was a missing-token like N/A -> blanked
        return cleaned, False, ""

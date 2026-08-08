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

        def _cap(w: str) -> str:
            lw = w.lower()
            if lw.startswith("o'") and len(lw) > 2:
                return "O'" + _cap(w[2:])
            if lw.startswith("mc") and len(lw) > 2:
                return "Mc" + w[2:].capitalize()
            return "-".join(p.capitalize() for p in w.split("-"))  # Mary-Jane, not Mary-jane

        parts = []
        for i, w in enumerate(s.split(" ")):
            lw = w.lower()
            if lw in self._particles and i > 0:      # particle lower-cased only mid-name
                parts.append(lw)
            else:
                parts.append(_cap(w))
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
    """Number parsing that respects the decimal point. A lone dot is a decimal
    (so 42.959 stays 42.959, not 42959); commas are thousands unless clearly a
    decimal comma (12,5). Handles currency symbols, %, and parentheses-negatives.
    A digit must be present, so 'free'/'N/A' are flagged, not zeroed."""
    name = "numeric"

    @staticmethod
    def _parse(s: str, convention: str = "dot"):
        st = s.strip()
        neg = (st.startswith("(") and st.endswith(")")) or st.startswith("-") or st.startswith("\u2212")
        pct = st.endswith("%")
        t = re.sub(r"[^0-9.,]", "", st)          # keep digits and separators only
        if t == "":
            return None, neg, pct
        has_c, has_d = "," in t, "." in t
        if has_c and has_d:
            if t.rfind(",") > t.rfind("."):       # 1.200,50 -> decimal comma
                t = t.replace(".", "").replace(",", ".")
            else:                                  # 1,200.50 -> thousands comma
                t = t.replace(",", "")
        elif convention == "comma":               # European column: comma is the decimal
            if has_c:
                if t.count(",") > 1:
                    t = t.replace(",", "")        # 1,234,567 -> thousands commas
                else:
                    t = t.replace(".", "").replace(",", ".")  # 1.234,56 handled above; 12,5 -> 12.5
            elif has_d:
                t = t.replace(".", "")            # dot is thousands here: 1.234 -> 1234
        else:                                      # dot convention (default)
            if has_c:
                parts = t.split(",")
                if len(parts) == 2 and len(parts[1]) in (1, 2):
                    t = parts[0] + "." + parts[1] # 12,5 -> 12.5 (decimal comma)
                else:
                    t = t.replace(",", "")        # 1,200 / 1,200,000 -> thousands
            elif has_d:
                if t.count(".") > 1:              # 1.234.567 -> thousands dots
                    t = t.replace(".", "")
                # single dot stays a decimal point
        try:
            val = float(t)
        except ValueError:
            return None, neg, pct
        return (-abs(val) if neg else val), neg, pct

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _clean_str(value)
        if s == "":
            return "", True, "empty numeric"
        if not any(ch.isdigit() for ch in s):
            return value, True, "not numeric (no digits)"
        convention = self.params.get("decimal", "dot")
        amount, neg, pct = self._parse(s, convention)
        if amount is None:
            return value, True, "not numeric"
        out = str(int(amount)) if float(amount).is_integer() else repr(amount)
        return out, False, ("read as percent value" if pct else "")


class TextNormaliseTransform(Transform):
    name = "text_normalise"

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _clean_str(value)
        if s == "":
            return "", False, ""
        try:
            import ftfy
            s = ftfy.fix_text(s)                       # repair mojibake (Ã© -> é)
        except Exception:
            pass
        s = (s.replace("\u2018", "'").replace("\u2019", "'")
              .replace("\u201c", '"').replace("\u201d", '"')
              .replace("\u2013", "-").replace("\u2014", "-"))
        return _clean_str(s), False, ""


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

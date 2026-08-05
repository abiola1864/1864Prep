"""Phone-number normalisation for Nigerian MSISDNs.

Turns the many forms agencies store (08031234567, 8031234567, 234803...,
+234 803 123 4567, with spaces or dashes) into one canonical +234XXXXXXXXXX.
Numbers that cannot be made into a valid 10-digit national number are kept and
flagged.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .base import Transform

# Valid Nigerian mobile network codes (national leading digits after the 0),
# e.g. 0703, 0803, 0906. We check the first three national digits.
_VALID_PREFIXES = {
    "700", "701", "702", "703", "704", "705", "706", "707", "708", "709",
    "800", "801", "802", "803", "804", "805", "806", "807", "808", "809",
    "810", "811", "812", "813", "814", "815", "816", "817", "818", "819",
    "900", "901", "902", "903", "904", "905", "906", "907", "908", "909",
    "911", "912", "913", "914", "915", "916", "917", "918",
}

_NON_DIGIT = re.compile(r"[^\d+]")


class PhoneNGTransform(Transform):
    name = "phone_ng"

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "", True, "empty phone"

        s = str(value).strip()
        if s.endswith(".0"):
            s = s[:-2]
        s = _NON_DIGIT.sub("", s)
        s = s.lstrip("+")

        # Reduce to the 10-digit national number.
        if s.startswith("234"):
            national = s[3:]
        elif s.startswith("0"):
            national = s[1:]
        else:
            national = s

        if len(national) != 10:
            return value, True, f"cannot resolve to 10-digit national number (got {len(national)})"

        if national[:3] not in _VALID_PREFIXES:
            return "+234" + national, True, f"unknown network prefix 0{national[:3]}"

        return "+234" + national, False, ""

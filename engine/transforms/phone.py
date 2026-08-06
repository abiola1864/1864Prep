"""Phone standardisation for ANY country, via Google's libphonenumber
(`phonenumbers`). The country is a parameter, not hard-coded: it defaults to the
active region's `phone_region`, so the same transform serves Nigeria, Kenya,
India or anywhere else."""
from __future__ import annotations

from typing import Any

import phonenumbers

from .base import Transform, _clean_str


class PhoneTransform(Transform):
    """params: region (ISO-3166 alpha-2, e.g. 'NG'); defaults to the active
    region. Output is E.164 (+<country><number>). Invalid numbers are flagged."""
    name = "phone"

    def __init__(self, **params):
        super().__init__(**params)
        region = params.get("region")
        if region is None:
            try:
                from regions import get_active_region
                region = get_active_region().phone_region
            except Exception:
                region = None
        self._region = region

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _clean_str(value)
        if s == "":
            return "", True, "empty phone"
        try:
            num = phonenumbers.parse(s, self._region)
        except phonenumbers.NumberParseException:
            return value, True, "could not parse phone number"
        if not phonenumbers.is_valid_number(num):
            return value, True, "not a valid phone number"
        return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164), False, ""


class PhoneNGTransform(PhoneTransform):
    """Nigeria-defaulted phone transform (kept for the plan key 'phone_ng')."""
    name = "phone_ng"

    def __init__(self, **params):
        params.setdefault("region", "NG")
        super().__init__(**params)

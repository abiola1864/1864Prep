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
            region = None
            for mod in ("regions", "engine.regions_fallback"):
                try:
                    m = __import__(mod, fromlist=["get_active_region"])
                    region = getattr(m.get_active_region(), "phone_region", None)
                    break
                except Exception:
                    continue
        self._region = region

    def run(self, series, source_column, target_field):
        # No region set (the Generic pack): work out the country from numbers in
        # this column that already carry one (+254..., 0044...), and use it for
        # the local numbers. International by design: nothing is assumed.
        if not self._region:
            from collections import Counter
            seen = Counter()
            for v in series.tolist()[:5000]:
                s = _clean_str(v).replace(" ", "")
                if s.startswith("00"):
                    s = "+" + s[2:]
                if s.startswith("+"):
                    try:
                        rc = phonenumbers.region_code_for_number(phonenumbers.parse(s, None))
                        if rc and rc != "ZZ":
                            seen[rc] += 1
                    except phonenumbers.NumberParseException:
                        pass
            if seen:
                self._region = seen.most_common(1)[0][0]
        return super().run(series, source_column, target_field)

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = _clean_str(value)
        if s == "":
            return "", True, "empty phone"
        if s.startswith("00") and s[2:3].isdigit():
            s = "+" + s[2:]
        if not self._region and not s.lstrip().startswith("+"):
            return value, True, "no country code: set your Region in Settings, or add the country code"
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

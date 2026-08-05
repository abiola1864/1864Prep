"""Service-provider normalisation, ported from the NCC script.

Anchored exact-match normalisation to a fixed set of MNOs and ISPs. Values that
don't match after normalisation are flagged (the R script DROPS these rows;
this engine flags and keeps by default -- see NOTES_R_ALIGNMENT.md).
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .base import Transform

MNO_PROVIDERS = ["Airtel", "MTN", "Glo", "T2"]
ISP_PROVIDERS = ["IPNX", "Legend", "Fiberone", "Spectranet", "Tizeti", "Smile",
                 "Coolink", "Starlink", "NGCOM", "Swift", "Cobranet",
                 "Iworld Networks", "Infratel", "Layer3"]
_KNOWN = set(MNO_PROVIDERS) | set(ISP_PROVIDERS)

# (regex on the trimmed raw value, canonical) -- anchored, order as in R.
_RULES = [
    (re.compile(r"^(Airtel|AIRTEL)$"), "Airtel"),
    (re.compile(r"^MTN$"), "MTN"),
    (re.compile(r"^(Glo|GLO)$"), "Glo"),
    (re.compile(r"^EMTS$"), "T2"),
    (re.compile(r"^IPNX$"), "IPNX"),
    (re.compile(r"^(Legend|LEGEND)$"), "Legend"),
    (re.compile(r"^(Fiberone|FiberOne|FIBREONE|FIBERONE)$"), "Fiberone"),
    (re.compile(r"^(Spectranet|SPECTRANET)$"), "Spectranet"),
    (re.compile(r"^(Tizeti|TIZETI)$"), "Tizeti"),
    (re.compile(r"^(Smile|SMILE)$"), "Smile"),
    (re.compile(r"^(Coolink|Coollink|COOLLINK)$"), "Coolink"),
    (re.compile(r"^(Starlink|STARLINK)$"), "Starlink"),
    (re.compile(r"^(Ngcom|NGCOM)$"), "NGCOM"),
    (re.compile(r"^(Swift|SWIFT)$"), "Swift"),
    (re.compile(r"^(Cobranet|COBRANET)$"), "Cobranet"),
    (re.compile(r"^(Iworld Networks|IWORLD NETWORKS)$"), "Iworld Networks"),
    (re.compile(r"^(Infratel|INFRATEL)$"), "Infratel"),
    (re.compile(r"^(Layer3|LAYER3)$"), "Layer3"),
]


class ProviderTransform(Transform):
    name = "provider"

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "", True, "empty provider"
        s = str(value).strip()
        for pat, canon in _RULES:
            if pat.match(s):
                return canon, False, ""
        if s in _KNOWN:
            return s, False, ""
        return value, True, "provider not in known MNO/ISP list (R drops these)"


class ProviderTypeTransform(Transform):
    """Maps a (already-normalised) provider to MNO / ISP."""
    name = "provider_type"

    def apply_value(self, value: Any) -> tuple[Any, bool, str]:
        s = str(value).strip()
        if s in MNO_PROVIDERS:
            return "MNO", False, ""
        if s in ISP_PROVIDERS:
            return "ISP", False, ""
        return "", True, "unknown provider type"

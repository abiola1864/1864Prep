"""A Region pack is *configuration*, not code. The engine is generic; a region
supplies the country-specific bits (default phone country, date order, currency
symbols, and optional reference lists). Swap the pack, clean another country's
data with the same engine."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Region:
    key: str
    name: str
    phone_region: str | None = None        # ISO-3166 alpha-2 for phonenumbers, e.g. "NG"
    date_order: str = "MDY"                # dateparser DATE_ORDER: "DMY" | "MDY" | "YMD"
    currency_symbols: tuple = ("$", "€", "£")
    states_ref: str | None = None          # path to a canonical list (optional)
    places_ref: str | None = None          # path to a place->admin gazetteer (optional)
    lga_refs: tuple = field(default_factory=tuple)   # optional sub-admin reference paths

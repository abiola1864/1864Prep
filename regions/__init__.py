"""Region registry + the active region.

GENERIC is the default and assumes nothing about any country — international
phone parsing, no built-in place lists. NG is one pack among many; adding
another country is a few lines here, not a change to the engine.
"""
from __future__ import annotations

from .base import Region

GENERIC = Region(
    key="generic",
    name="Generic / international",
    phone_region=None,                       # let phonenumbers infer from + prefix
    date_order="MDY",
    currency_symbols=("$", "€", "£", "₦", "₹", "¥", "R", "kr"),
)

NG = Region(
    key="ng",
    name="Nigeria",
    phone_region="NG",
    date_order="DMY",
    currency_symbols=("₦", "N", "#"),
    states_ref="reference/ng_states_canonical.json",
    places_ref="reference/ng_places_gazetteer.json",
    lga_refs=("reference/ng_lga_kaduna.json",),
)

_REGISTRY = {r.key: r for r in (GENERIC, NG)}
_active: Region = GENERIC


def get_region(key: str) -> Region:
    return _REGISTRY.get((key or "").lower(), GENERIC)


def list_regions() -> list[str]:
    return sorted(_REGISTRY)


def register_region(region: Region) -> None:
    _REGISTRY[region.key] = region


def set_active_region(key_or_region) -> Region:
    global _active
    _active = key_or_region if isinstance(key_or_region, Region) else get_region(key_or_region)
    return _active


def get_active_region() -> Region:
    return _active


def load_reference(region: Region | None = None) -> dict:
    """Load a region's reference data into the shapes the profiler/pipeline use.

    Returns {gazetteers, place_index, gazetteer_refs}. For GENERIC (no place
    lists) everything is empty and geo detection simply doesn't fire — the engine
    still cleans everything else. This is the seam that keeps Nigeria a *pack*:
    swap the region, get different reference data, same engine.
    """
    import json
    from pathlib import Path

    region = region or get_active_region()
    root = Path(__file__).resolve().parents[1]
    gazetteers: dict[str, str] = {}
    place_index: dict[str, set] = {}
    gazetteer_refs: dict[str, str] = {}

    if region.states_ref:
        ref = root / region.states_ref
        if ref.exists():
            data = json.loads(ref.read_text(encoding="utf-8"))
            names = data.get("states") or data.get("canonical") or data
            canon = list(names.keys()) if isinstance(names, dict) else list(names)
            gazetteers["state"] = {c: c for c in canon}
            gazetteer_refs["state"] = region.states_ref
            place_index["state"] = set()

    if region.places_ref:
        ref = root / region.places_ref
        if ref.exists():
            places = json.loads(ref.read_text(encoding="utf-8"))
            mapping = places.get("places", places) if isinstance(places, dict) else {}
            if "state" in gazetteers and isinstance(mapping, dict):
                place_index["state"] = set(mapping.keys())

    return {"gazetteers": gazetteers or None,
            "place_index": place_index or None,
            "gazetteer_refs": gazetteer_refs}

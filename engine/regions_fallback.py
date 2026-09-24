"""Built-in minimal region handler.

Used automatically only when the richer top-level `regions.py` is not present
(e.g. a standalone build). Keeps the app fully runnable offline; reference
matching is empty in this mode, which the app already handles gracefully.
"""
from dataclasses import dataclass


@dataclass
class Region:
    code: str = "generic"
    name: str = "Generic"


_ACTIVE = Region()
_REGIONS = {"generic": Region("generic", "Generic"), "ng": Region("ng", "Nigeria")}


def set_active_region(code):
    global _ACTIVE
    _ACTIVE = _REGIONS.get(code, Region(code or "generic", (code or "generic").title()))
    return _ACTIVE


def get_active_region():
    return _ACTIVE


def get_region(code):
    return _REGIONS.get(code, _ACTIVE)


def list_regions():
    return list(_REGIONS.values())


def load_reference():
    return {"gazetteers": {}, "place_index": {}, "gazetteer_refs": {}}

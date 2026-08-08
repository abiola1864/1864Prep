"""Nigeria administrative resolver: validate and standardise State and LGA
columns against the complete official set (36 states + FCT, 774 LGAs), with
typo tolerance and honest flagging.

This is the general "check against the known universe" pattern applied to
Nigerian admin levels:
  * exact or near-exact match -> standardise ("kastna" -> "Katsina").
  * value that is really a different level (a State in an LGA column, or a known
    LGA in a State column) -> flag the level mismatch.
  * value that matches nothing in the universe -> flag as unknown (often a city
    or community entered where an LGA was expected).

Data: reference/ng_states_lgas.json (MIT-licensed, all 774 LGAs).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_REF = Path(__file__).resolve().parent.parent / "reference" / "ng_states_lgas.json"


def _norm(s: str) -> str:
    s = str(s).strip().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def _data():
    try:
        d = json.loads(_REF.read_text())
    except Exception:
        return None
    states = d["states"]
    all_lgas = d["all_lgas"]
    return {
        "states": states,
        "all_lgas": all_lgas,
        "state_norm": {_norm(s): s for s in states},
        "lga_norm": {_norm(l): l for l in all_lgas},
        "lga_to_state": d.get("lga_to_state", {}),
    }


_STATE_ALIASES = {
    "fct": "Federal Capital Territory", "abuja": "Federal Capital Territory",
    "fct abuja": "Federal Capital Territory", "f c t": "Federal Capital Territory",
}


def _exact(value: str, canon_map: dict):
    return canon_map.get(_norm(value))


def _best(value: str, canon_map: dict):
    """Return (canonical, score) of the closest entry using full-string ratio
    (no partial matching, so short names like 'Oyi' don't swallow 'Ikoyi')."""
    try:
        from rapidfuzz import process, fuzz
        hit = process.extractOne(_norm(value), list(canon_map.keys()), scorer=fuzz.ratio)
        return (canon_map[hit[0]], hit[1]) if hit else (None, 0)
    except Exception:
        return (None, 0)


_AUTO = 82      # standardise silently at/above this
_SUGGEST = 70   # only suggest (flag for confirmation) between this and _AUTO


def _fuzzy(value: str, canon_map: dict, cutoff: int):
    canon, score = _best(value, canon_map)
    return canon if score >= cutoff else None


def resolve_state(value: str, fuzzy: bool = True):
    d = _data()
    if not d:
        return None
    return (_exact(value, d["state_norm"]) or _STATE_ALIASES.get(_norm(value))
            or (_fuzzy(value, d["state_norm"], _AUTO) if fuzzy else None))


def resolve_lga(value: str, fuzzy: bool = True):
    d = _data()
    if not d:
        return None
    return _exact(value, d["lga_norm"]) or (_fuzzy(value, d["lga_norm"], _AUTO) if fuzzy else None)


def looks_like(values, level: str, sample: int = 200) -> float:
    """Share of a column's values that resolve to a real state / LGA."""
    d = _data()
    if not d:
        return 0.0
    vals = [str(v).strip() for v in values if str(v).strip()][:sample]
    if not vals:
        return 0.0
    fn = resolve_state if level == "state" else resolve_lga
    return sum(1 for v in vals if fn(v)) / len(vals)


def validate_lga_value(value: str) -> dict:
    """Classify one value in an LGA column.
    kind: 'lga' (ok), 'is_state' (level mismatch), 'unknown' (city/community?)."""
    d = _data()
    exact_lga = _exact(value, d["lga_norm"]) if d else None
    if exact_lga:
        return {"kind": "lga", "canonical": exact_lga, "state": d["lga_to_state"].get(exact_lga)}
    if resolve_state(value, fuzzy=False):                       # a real State sitting in an LGA column
        return {"kind": "is_state", "canonical": resolve_state(value, fuzzy=False),
                "note": "this is a State, not an LGA"}
    typo_lga = resolve_lga(value)                               # near-match handles real typos
    if typo_lga:
        return {"kind": "lga", "canonical": typo_lga, "state": d["lga_to_state"].get(typo_lga)}
    cand, score = _best(value, d["lga_norm"]) if d else (None, 0)
    if cand and score >= _SUGGEST:
        return {"kind": "unknown", "canonical": None, "suggestion": cand,
                "note": f"not a known LGA - did you mean {cand}?"}
    return {"kind": "unknown", "canonical": None,
            "note": "not a known LGA (a city or community?)"}


def validate_state_value(value: str) -> dict:
    d = _data()
    exact_state = (_exact(value, d["state_norm"]) or _STATE_ALIASES.get(_norm(value))) if d else None
    if exact_state:
        return {"kind": "state", "canonical": exact_state}
    if d and _exact(value, d["lga_norm"]):
        return {"kind": "is_lga", "canonical": _exact(value, d["lga_norm"]),
                "note": "this is an LGA, not a State"}
    typo = resolve_state(value)
    if typo:
        return {"kind": "state", "canonical": typo}
    cand, score = _best(value, d["state_norm"]) if d else (None, 0)
    if cand and score >= _SUGGEST:
        return {"kind": "unknown", "canonical": None, "suggestion": cand,
                "note": f"not a known State - did you mean {cand}?"}
    return {"kind": "unknown", "canonical": None, "note": "not a known State"}

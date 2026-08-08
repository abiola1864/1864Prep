"""Optional person-name intelligence via the `names-dataset` package (a large,
offline global names dataset that covers Nigerian names well - Yoruba, Igbo,
Hausa - with per-country popularity and gender).

Honest scope:
  * gender from a first name is a PROBABILITY, never a fact. Unisex names (e.g.
    Oluwaseun) come back near 50/50 and are reported as 'unknown'.
  * this never overwrites data. It only produces a suggested, clearly-labelled
    estimate the user can accept or ignore.

Install once (offline afterwards):  pip install names-dataset
If absent, every function returns None and the engine is unaffected.
"""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _nd():
    try:
        from names_dataset import NameDataset
        return NameDataset()
    except Exception:
        return None


def available() -> bool:
    return _nd() is not None


def _first_token(full: str) -> str:
    parts = str(full).strip().split()
    return parts[0] if parts else ""


def name_gender(full_name: str, min_conf: float = 0.65) -> tuple[str | None, float]:
    """(estimate, confidence) where estimate is 'Male'/'Female'/None. Returns
    None when unavailable or when the name is genuinely unisex/unknown."""
    nd = _nd()
    if nd is None:
        return None, 0.0
    tok = _first_token(full_name)
    if len(tok) < 2:
        return None, 0.0
    try:
        info = (nd.search(tok) or {}).get("first_name") or {}
    except Exception:
        return None, 0.0
    g = info.get("gender") or {}
    if not g:
        return None, 0.0
    label, p = max(g.items(), key=lambda kv: kv[1])
    if p < min_conf:
        return None, round(p, 2)          # too close to call -> unknown, honestly
    return ("Male" if label.lower().startswith("m") else "Female"), round(p, 2)


def looks_like_person_names(values, sample: int = 60) -> float:
    """Share of a column's values whose first token is a known personal name.
    Works for Nigerian names. Use as a signal that a column holds people."""
    nd = _nd()
    if nd is None:
        return 0.0
    vals = [str(v).strip() for v in values if str(v).strip()][:sample]
    if not vals:
        return 0.0
    hits = 0
    for v in vals:
        tok = _first_token(v)
        try:
            if tok and (nd.search(tok) or {}).get("first_name"):
                hits += 1
        except Exception:
            pass
    return hits / len(vals)

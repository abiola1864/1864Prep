"""Domain packs for entity-heavy data (social protection and similar).

A *domain* is a closed set of real-world entities (countries, currencies, ID
types, sex, relationship-to-head, disability status, payment channel). Each has a
gazetteer: canonical name -> known variants/abbreviations/spellings.

Two jobs:
  1. resolve a messy value to its canonical entity ("naija" -> "Nigeria").
  2. tell whether two values are the SAME entity, so string-similarity merges
     never collapse different entities that merely look alike ("Niger" vs
     "Nigeria", "Iceland" vs "Ireland", "Congo, Dem. Rep." vs "Congo, Rep.").

Gazetteers are plain JSON under reference/domains/, so the full official lists
can be dropped in later without code changes.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_REF = Path(__file__).resolve().parents[2] / "reference" / "domains"


def _norm(s: str) -> str:
    s = str(s).strip().lower()
    s = re.sub(r"[\u2019']", "'", s)
    s = re.sub(r"[^a-z0-9'&\- ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def _load() -> dict:
    """Return {domain_name: {canonical: set(normalised variants)}}."""
    packs: dict[str, dict[str, set]] = {}
    # countries
    try:
        c = json.loads((_REF / "countries.json").read_text())
        packs["country"] = {canon: {_norm(canon), *[_norm(v) for v in vs]} for canon, vs in c["entries"].items()}
    except Exception:
        pass
    # social protection bundle
    try:
        sp = json.loads((_REF / "social_protection.json").read_text())
        for dom, entries in sp.items():
            packs[dom] = {canon: {_norm(canon), *[_norm(v) for v in vs]} for canon, vs in entries.items()}
    except Exception:
        pass
    return packs


def list_domains() -> list[str]:
    return list(_load().keys())


def _lookup(domain: str, value: str) -> str | None:
    v = _norm(value)
    if not v:
        return None
    for canon, variants in _load().get(domain, {}).items():
        if v in variants:
            return canon
    return None


def detect_domain(values, header: str = "") -> str | None:
    """Pick the domain whose gazetteer explains the most values (>=60%)."""
    vals = [str(x).strip() for x in values if str(x).strip()]
    if not vals:
        return None
    sample = vals[:200]
    best, best_rate = None, 0.0
    for dom in _load():
        hits = sum(1 for v in sample if _lookup(dom, v) is not None)
        rate = hits / len(sample)
        if rate > best_rate:
            best, best_rate = dom, rate
    # header hint can lower the bar a little
    h = _norm(header)
    hint = {"country": ["country", "nationality"], "sex": ["sex", "gender"],
            "currency": ["currency", "curr"], "id_type": ["id type", "idtype", "id"],
            "relationship_to_head": ["relationship", "relation to head"],
            "disability_status": ["disability", "impairment"],
            "payment_channel": ["payment", "channel", "payment method"]}
    threshold = 0.6
    if best and any(k in h for k in hint.get(best, [])):
        threshold = 0.4
    return best if best_rate >= threshold else None


def resolve_value(domain: str, value: str) -> tuple[str, bool]:
    """(canonical, changed). Unknown values are returned unchanged."""
    canon = _lookup(domain, value)
    if canon is None:
        return value, False
    return canon, (canon != str(value).strip())


def canonical_of(domain: str, value: str) -> str | None:
    """The canonical entity for a value, or None if not in the gazetteer."""
    return _lookup(domain, value)


def same_entity(domain: str, a: str, b: str) -> bool | None:
    """True/False if both map to gazetteer entities; None if either is unknown
    (caller should fall back to string similarity only then)."""
    ca, cb = _lookup(domain, a), _lookup(domain, b)
    if ca is None or cb is None:
        return None
    return ca == cb

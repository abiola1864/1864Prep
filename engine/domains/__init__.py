"""Domain packs for entity-heavy data (social protection and similar).

Named entities are resolved with real packages, not hand lists:

  * country  -> `country_converter` (coco): harmonises ISO / UN / World Bank
    names ("Congo, Dem. Rep.", "Korea, Rep.", "Hong Kong SAR, China", "Lao PDR")
    to ISO3 codes. Identity is the ISO3 code, so different countries that merely
    look alike ("Niger" NER vs "Nigeria" NGA) are never treated as the same.

  * a handful of survey-specific categoricals that NO package covers (sex,
    relationship-to-head, disability status, payment channel, ID type) use a
    small JSON gazetteer under reference/domains/. These are genuinely small,
    closed sets, not country-style lists.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

_REF = Path(__file__).resolve().parents[2] / "reference" / "domains"
logging.getLogger("country_converter").setLevel(logging.ERROR)


@lru_cache(maxsize=1)
def _coco():
    try:
        import country_converter as coco
        return coco.CountryConverter()
    except Exception:
        return None


@lru_cache(maxsize=8192)
def _country_iso(value: str) -> str | None:
    v = str(value).strip()
    if len(v) < 2 or v.isdigit():
        return None
    cc = _coco()
    if cc is None:
        return None
    try:
        iso = cc.convert(v, to="ISO3", not_found=None)
    except Exception:
        return None
    return iso or None


@lru_cache(maxsize=4096)
def _country_name(iso: str) -> str | None:
    cc = _coco()
    if cc is None or not iso:
        return None
    try:
        name = cc.convert(iso, src="ISO3", to="name_short", not_found=None)
    except Exception:
        return None
    return name or None


# ── currency + world admin regions via pycountry (offline, package data) ─────
@lru_cache(maxsize=8192)
def _currency_code(value: str) -> str | None:
    v = str(value).strip()
    if len(v) < 1:
        return None
    try:
        import pycountry
        return pycountry.currencies.lookup(v).alpha_3
    except Exception:
        return None


@lru_cache(maxsize=1)
def _subdiv_map() -> dict:
    """Normalised subdivision name -> set of pycountry codes (states/provinces/
    counties for every country)."""
    m: dict[str, set] = {}
    try:
        import pycountry
        for s in pycountry.subdivisions:
            m.setdefault(_norm(s.name), set()).add(s.code)
    except Exception:
        pass
    return m


def _subdiv_id(value: str) -> str | None:
    codes = _subdiv_map().get(_norm(value))
    if not codes:
        return None
    return sorted(codes)[0] if len(codes) == 1 else "AMBIG:" + _norm(value)


def _subdiv_name(ident: str) -> str | None:
    if not ident or ident.startswith("AMBIG:"):
        return None
    try:
        import pycountry
        s = pycountry.subdivisions.get(code=ident)
        return s.name if s else None
    except Exception:
        return None


def _norm(s: str) -> str:
    s = str(s).strip().lower()
    s = re.sub(r"[\u2019']", "'", s)
    s = re.sub(r"[^a-z0-9'&\- ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def _json_domains() -> dict:
    packs: dict[str, dict[str, set]] = {}
    try:
        sp = json.loads((_REF / "social_protection.json").read_text())
        for dom, entries in sp.items():
            packs[dom] = {canon: {_norm(canon), *[_norm(v) for v in vs]} for canon, vs in entries.items()}
    except Exception:
        pass
    return packs


def _json_lookup(domain: str, value: str) -> str | None:
    v = _norm(value)
    if not v:
        return None
    for canon, variants in _json_domains().get(domain, {}).items():
        if v in variants:
            return canon
    return None


def list_domains() -> list[str]:
    return ["ng_lga", "ng_state", "country", "currency", "subdivision", *_json_domains().keys()]


def _identity(domain: str, value: str) -> str | None:
    if domain == "country":
        return _country_iso(value)
    if domain == "currency":
        return _currency_code(value)
    if domain == "subdivision":
        return _subdiv_id(value)
    if domain in ("ng_state", "ng_lga"):
        from . import _ng_ident
        return _ng_ident(domain, value)
    return _json_lookup(domain, value)


def detect_domain(values, header: str = "") -> str | None:
    vals = [str(x).strip() for x in values if str(x).strip()]
    if not vals:
        return None
    sample = vals[:200]
    h = _norm(header)
    hint = {"country": ["country", "nationality", "nation"], "sex": ["sex", "gender"],
            "currency": ["currency", "curr"], "id_type": ["id type", "idtype"],
            "subdivision": ["state", "province", "region", "county", "lga", "district"],
            "relationship_to_head": ["relationship", "relation"],
            "disability_status": ["disability", "impairment"],
            "payment_channel": ["payment", "channel"],
            "ng_state": ["state", "state of origin"], "ng_lga": ["lga", "local government", "l.g.a"]}

    def rate(dom):
        return sum(1 for v in sample if _identity(dom, v) is not None) / len(sample)

    # specific domains first; country (greedy fuzzy) is the fallback
    order = ["ng_lga", "ng_state", "subdivision", "currency", "sex", "relationship_to_head",
             "disability_status", "payment_channel", "id_type", "country"]
    order = [d for d in order if d in list_domains()]
    for dom in order:
        thr = 0.4 if any(k in h for k in hint.get(dom, [])) else 0.6
        if rate(dom) >= thr:
            return dom
    return None


def resolve_value(domain: str, value: str) -> tuple[str, bool]:
    if domain == "country":
        iso = _country_iso(value)
        name = _country_name(iso) if iso else None
        return (name, name != str(value).strip()) if name else (value, False)
    if domain == "currency":
        code = _currency_code(value)
        return (code, code != str(value).strip()) if code else (value, False)
    if domain == "subdivision":
        name = _subdiv_name(_subdiv_id(value) or "")
        return (name, name != str(value).strip()) if name else (value, False)
    if domain in ("ng_state", "ng_lga"):
        c = _ng_ident(domain, value)
        return (c, c != str(value).strip()) if c else (value, False)
    canon = _json_lookup(domain, value)
    if canon is None:
        return value, False
    return canon, (canon != str(value).strip())


def canonical_of(domain: str, value: str) -> str | None:
    return _identity(domain, value)


def _ng_ident(domain, value):
    try:
        from ..ng_admin import resolve_state, resolve_lga
        c = resolve_state(value) if domain == "ng_state" else resolve_lga(value)
        return c
    except Exception:
        return None


def same_entity(domain: str, a: str, b: str) -> bool | None:
    ca, cb = _identity(domain, a), _identity(domain, b)
    if ca is None or cb is None:
        return None
    return ca == cb

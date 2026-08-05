"""Per-field 'perfect world' prediction + guided adjustment.

For every column the tool first PREDICTS what the field ideally is -- its
canonical name, its type, the target standard/format, and (for categorical/geo
fields) the ideal standardised values -- then produces the specific questions to
walk the user through confirming or adjusting that prediction. It leans on the
correction memory (engine/knowledge.py), so everything the team has already
taught it is applied, and every answer teaches it more.

Designed for files with MANY fields: each field yields one compact, self-
contained review item.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from .induce import induce_vocabulary
from .knowledge import CorrectionStore
from .profile import profile_column
from .resolve import EntityResolver

# Canonical field-name prediction from header synonyms (itself extensible /
# learnable -- a header the tool hasn't seen becomes a new synonym once mapped).
_FIELD_SYNONYMS = {
    "NIN": ["nin", "ninnumber", "nationalid", "national id number"],
    "BVN": ["bvn", "bvnno", "bvnnumber", "bankverificationnumber"],
    "Phone (MSISDN)": ["phone", "phno", "phonenumber", "mobile", "gsm", "msisdn", "tel", "cell", "altphone"],
    "Email": ["email", "emailaddress", "mail"],
    "First Name": ["firstname", "othernames", "givenname", "forename"],
    "Last Name": ["surname", "lastname", "familyname"],
    "Full Name": ["fullname", "name"],
    "Gender": ["gender", "sex"],
    "Date of Birth": ["dob", "dateofbirth", "birthdate"],
    "State": ["state", "stateoforigin", "homestate", "facilitystate", "state of residence"],
    "LGA": ["lga", "localgovt", "localgovernment", "localgovernmentarea"],
    "Household ID": ["householdid", "hhid"],
    "Address": ["address", "residentialaddress", "homeaddress", "addr"],
}
_norm = lambda s: re.sub(r"[^a-z0-9]+", "", str(s).strip().lower())
_SYN_LOOKUP = {_norm(a): canon for canon, al in _FIELD_SYNONYMS.items() for a in al}

# When the header names a known field, it is a strong prior for what the field
# IS -- stronger than a low-confidence statistical guess. (canonical name ->
# (semantic_type, transform, gazetteer_or_None))
_NAME_TYPE = {
    "Phone (MSISDN)": ("phone", "phone_ng", None),
    "NIN": ("identifier", "nin", None),
    "BVN": ("identifier", "nin", None),
    "Email": ("email", "email", None),
    "First Name": ("name", "name", None),
    "Last Name": ("name", "name", None),
    "Full Name": ("name", "name", None),
    "Gender": ("gender", "gender", None),
    "Date of Birth": ("date", "date_iso", None),
    "State": ("geo", "resolve", "ng_state"),
    "LGA": ("geo", "resolve", "ng_lga"),
    "Address": ("free_text", "text_normalise", None),
}

_TARGET_STANDARD = {
    "identifier": "digits only, fixed length (validated)",
    "phone": "+234XXXXXXXXXX  (E.164)",
    "email": "lowercase, valid address",
    "date": "ISO 8601  YYYY-MM-DD",
    "gender": "M / F",
    "boolean": "Yes / No",
    "geo": "official canonical value (e.g. one of 37 states, UPPERCASE)",
    "numeric": "number (decimal); units per field",
    "categorical": "one of a standardised set of categories",
    "name": "Title Case, trimmed",
    "free_text": "trimmed, whitespace-normalised",
}


@dataclass
class FieldSpec:
    source_column: str
    predicted_name: str
    semantic_type: str
    transform: str | None
    target_standard: str
    confidence: float
    questions: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


def predict_name(source_column: str) -> tuple[str, bool]:
    hit = _SYN_LOOKUP.get(_norm(source_column))
    if hit:
        return hit, True
    # fallback: tidy the raw header
    return re.sub(r"[_\.]+", " ", str(source_column)).strip().title(), False


def predict_field(series: pd.Series, source_column: str,
                  store: CorrectionStore | None = None,
                  gazetteers: dict | None = None) -> FieldSpec:
    store = store or CorrectionStore()
    # feed learned corrections into type detection as "known places"
    place_index = {g: set(store.memory(g).keys()) for g in (gazetteers or {})}
    prof = profile_column(series, source_column, gazetteers, place_index)
    pname, name_known = predict_name(source_column)

    # header prior: a recognised field name decides the TYPE when it disagrees
    # with a low-confidence statistical guess.
    if name_known and pname in _NAME_TYPE:
        ftype, ftransform, fgaz = _NAME_TYPE[pname]
        if ftype != prof.semantic_type and prof.confidence <= 0.85:
            from dataclasses import replace as _replace
            params = dict(prof.params)
            if fgaz:
                params["gazetteer"] = fgaz
            prof = _replace(prof, semantic_type=ftype, transform=ftransform,
                            params=params, confidence=max(prof.confidence, 0.8))
    target = _TARGET_STANDARD.get(prof.semantic_type, "standardised value")
    spec = FieldSpec(source_column, pname, prof.semantic_type, prof.transform,
                     target, round(prof.confidence, 2))

    # field-name question if we're not sure
    if not name_known:
        spec.questions.append(f"I'll name this field '{pname}'. Rename it?")

    t = prof.semantic_type
    if t == "identifier":
        length = prof.params.get("length", prof.evidence.get("id_length"))
        spec.details["length"] = length
        if length == 11:
            spec.predicted_name = "NIN" if _norm(source_column) in {"nin"} else spec.predicted_name
            spec.questions.append(
                "This is an 11-digit ID. Is it a NIN, a BVN, or another 11-digit identifier? "
                "(format alone can't tell them apart)")
        else:
            spec.questions.append(f"Treat as an identifier of {length} digits — correct?")

    elif t == "date":
        spec.questions.append("Are these dates day-first (DD/MM) or month-first (MM/DD)? "
                              "I'll standardise all to YYYY-MM-DD.")

    elif t == "phone":
        spec.questions.append("Normalise all numbers to +234 (E.164)? Non-Nigerian numbers will be flagged.")

    elif t == "geo":
        gaz = prof.params.get("gazetteer", "ng_state")
        canonical = (gazetteers or {}).get(gaz, [])
        resolver = EntityResolver(canonical, memory=store.memory(gaz))
        distinct = sorted({str(v).strip() for v in series.dropna() if str(v).strip()})
        learned = review = unresolved = 0
        conflicts, unresolved_vals = [], []
        for v in distinct:
            kind, cand = store.lookup(gaz, v)
            if kind == "conflict":
                conflicts.append((v, cand)); continue
            m = resolver.resolve(v)
            if m.method == "learned":
                learned += 1
            elif m.band == "high":
                review += 0  # auto-accepted by similarity
            elif m.band == "review":
                review += 1
            else:
                unresolved += 1; unresolved_vals.append(v)
        spec.details.update({"distinct": len(distinct), "learned": learned,
                             "needs_review": review, "unresolved": unresolved_vals[:10],
                             "conflicts": conflicts[:10]})
        spec.questions.append(f"{len(distinct)} distinct values: {learned} resolved from what "
                              f"you've taught me, {review} to confirm.")
        if unresolved_vals:
            spec.questions.append(f"{len(unresolved_vals)} I can't place — e.g. {unresolved_vals[:5]}. "
                                  "Tell me the state for each and I'll remember it.")
        if conflicts:
            spec.questions.append(f"{len(conflicts)} conflict(s) from past data — e.g. "
                                  f"{conflicts[0][0]} could be {conflicts[0][1]}. Which is right?")

    elif t == "categorical":
        vocab = induce_vocabulary(series.tolist())
        spec.details.update({"n_raw": vocab.n_raw, "categories": sorted(vocab.clusters)})
        spec.questions.append(f"I see {vocab.n_raw} spellings that group into {vocab.n_canonical} "
                              f"categories: {sorted(vocab.clusters)}. Confirm or rename these labels?")

    elif t == "numeric":
        spec.questions.append("Treat as a numeric measure? Tell me the unit (e.g. NGN, hectares) if relevant.")

    elif t == "name":
        spec.questions.append("Standardise to Title Case and trim? Split into first/last if needed?")

    return spec


def predict_file(df: pd.DataFrame, store: CorrectionStore | None = None,
                 gazetteers: dict | None = None) -> list[FieldSpec]:
    store = store or CorrectionStore()
    return [predict_field(df[c], c, store, gazetteers) for c in df.columns]

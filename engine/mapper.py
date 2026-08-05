"""Rules-first schema mapper (offline, no model).

This is the first rung of the mapping ladder from the technical design: before
any model is involved, an alias dictionary plus light fuzzy matching resolves
most columns. It looks only at column *headers* and a few sample values to pick
a target field and transform — it never scans the full dataset. The output is a
plan (the same JSON the pipeline executes and a human can edit).

When a header is ambiguous or unknown, the column is left unmapped and reported,
so a person (or, later, a local model — rung 2) can decide. Nothing is guessed
silently.
"""
from __future__ import annotations

import difflib
import re
from typing import Any

import pandas as pd

_NORM = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    return _NORM.sub("", str(s).strip().lower())


# Header alias -> (target_field, transform, params). Extend this dictionary as
# you meet new agency conventions; it is the cheap, owned asset the doc argues
# is more valuable than a bespoke model.
HEADER_ALIASES: dict[str, tuple[str, str, dict]] = {
    "nin": ("NIN", "nin", {}),
    "ninnumber": ("NIN", "nin", {}),
    "nationalid": ("NIN", "nin", {}),
    "phno": ("MSISDN", "phone_ng", {}),
    "phone": ("MSISDN", "phone_ng", {}),
    "phonenumber": ("MSISDN", "phone_ng", {}),
    "mobile": ("MSISDN", "phone_ng", {}),
    "msisdn": ("MSISDN", "phone_ng", {}),
    "gsm": ("MSISDN", "phone_ng", {}),
    "surname": ("Last Name", "name", {}),
    "lastname": ("Last Name", "name", {}),
    "othernames": ("First Name", "name", {}),
    "firstname": ("First Name", "name", {}),
    "givenname": ("First Name", "name", {}),
    "dob": ("Date of Birth", "date_iso", {"dayfirst": True}),
    "dateofbirth": ("Date of Birth", "date_iso", {"dayfirst": True}),
    "birthdate": ("Date of Birth", "date_iso", {"dayfirst": True}),
    "sex": ("Gender", "gender", {}),
    "gender": ("Gender", "gender", {}),
    "state": ("State", "state_ng", {"reference": "reference/ng_states.json"}),
    "stateoforigin": ("State", "state_ng", {"reference": "reference/ng_states.json"}),
    "lga": ("LGA", "lga_ng", {"reference": "reference/ng_lga_kaduna.json"}),
    "localgovt": ("LGA", "lga_ng", {"reference": "reference/ng_lga_kaduna.json"}),
    "householdid": ("Household ID", "upper", {}),
    "hhid": ("Household ID", "upper", {}),
}


def propose_plan(df: pd.DataFrame, plan_name: str = "auto", fuzzy_cutoff: float = 0.82) -> dict:
    """Build a plan from the DataFrame's *headers* (and nothing else).

    Returns a dict with 'mappings' (confident matches) and 'unmapped'
    (columns a human/model should decide on). Confidence is recorded so the
    review UI can sort by it, mirroring the mockup's step 4.
    """
    keys = list(HEADER_ALIASES.keys())
    mappings: list[dict] = []
    unmapped: list[dict] = []

    for col in df.columns:
        nk = _norm(col)
        if nk in HEADER_ALIASES:
            tgt, tf, params = HEADER_ALIASES[nk]
            mappings.append(_mapping(col, tgt, tf, params, "high", 1.0))
            continue

        match = difflib.get_close_matches(nk, keys, n=1, cutoff=fuzzy_cutoff)
        if match:
            tgt, tf, params = HEADER_ALIASES[match[0]]
            score = difflib.SequenceMatcher(None, nk, match[0]).ratio()
            conf = "medium" if score < 0.95 else "high"
            mappings.append(_mapping(col, tgt, tf, params, conf, round(score, 2)))
        else:
            unmapped.append({"source_column": col, "reason": "no dictionary or fuzzy match"})

    return {
        "name": plan_name,
        "generated_by": "rules-first mapper (offline, no model)",
        "mappings": mappings,
        "unmapped": unmapped,
    }


def _mapping(src, tgt, tf, params, conf, score) -> dict:
    return {
        "source_column": src,
        "target_field": tgt,
        "transform": tf,
        "params": params,
        "confidence": conf,
        "score": score,
    }


def sample_payload(df: pd.DataFrame, n_rows: int = 3) -> dict:
    """The ONLY thing a model would ever see (rung 2+): headers and a few
    sample values. Provided here so it is explicit and inspectable — the "what
    gets sent" preview the technical doc requires. The full dataset is never
    part of this payload.
    """
    return {
        "headers": list(df.columns),
        "sample_rows": df.head(n_rows).astype(str).to_dict(orient="records"),
        "row_count": len(df),
        "note": "Only these headers and sample rows would ever leave the machine, and only if a remote model were explicitly enabled. The default mapper uses no model at all.",
    }

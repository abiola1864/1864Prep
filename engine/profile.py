"""Column profiling: infer what an arbitrary column IS, from the data alone.

This is what lets the tool handle a health file, an agric file, a pension file
-- schemas it has never seen -- without sector-specific configuration. For each
column it reads the values and infers a semantic type, then recommends a
transform. Nothing here is tied to a fixed schema; it is all evidence from the
data (formats, cardinality, lengths, dictionary hit-rates).

Inferred semantic types and the transform each implies:
    identifier   -> fixed_id (with detected length; nin if length 11)
    phone        -> phone_ng
    email        -> email (lower/trim)
    date         -> date_iso
    boolean      -> boolean
    gender       -> gender
    geo          -> resolve (against a supplied gazetteer)
    categorical  -> induce_vocabulary  (unknown vocab, discovered from data)
    numeric      -> numeric
    name         -> name
    free_text    -> text_normalise
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd
from dateutil import parser as dtparser

from .resolve import EntityResolver

_DIGITS = re.compile(r"^\d+$")
_PHONE = re.compile(r"^(\+?234|0)\d{9,10}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NUMERIC = re.compile(r"^-?\d+(\.\d+)?$")
_BOOL = {"yes", "no", "true", "false", "y", "n", "1", "0"}
_GENDER = {"m", "f", "male", "female", "man", "woman", "boy", "girl"}


def _clean_vals(series: pd.Series) -> list[str]:
    out = []
    for v in series.tolist():
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        s = str(v).strip()
        if s == "" or s.lower() in {"na", "n/a", "#n/a", "nan", "null", "none", "[null]", "[na]", "nil", "-", "--"}:
            continue
        out.append(s)
    return out


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _norm_key(s: str) -> str:
    import re as _re
    return _re.sub(r'[^a-z0-9]+', ' ', str(s).strip().lower()).strip()


def _rate(vals, pred) -> float:
    return sum(1 for v in vals if pred(v)) / len(vals) if vals else 0.0


def _date_ok(s: str) -> bool:
    if _NUMERIC.match(s) and "." not in s and len(s) <= 6:
        return False  # bare small ints are not dates
    try:
        dtparser.parse(s, dayfirst=False)
        return True
    except Exception:
        return False


@dataclass
class ColumnProfile:
    column: str
    semantic_type: str
    confidence: float
    transform: str | None
    params: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)


_HEADER_HINTS = [
    (r"(?:^|[_\s])(lat|latitude|gpslat|lat_?dd)(?:$|[_\s0-9])", "latitude"),
    (r"(?:^|[_\s])(lon|lng|long|longitude|gpslon|gpslng|lon_?dd)(?:$|[_\s0-9])", "longitude"),
    (r"(gps|geopoint|geo_?point|geo_?location|coord|coordinate|coordinates|location|lat_?long|latlon)", "geopoint"),
    (r"(e-?mail)", "email"),
    (r"(?:^|[_\s])(phone|mobile|gsm|msisdn|tel)(?:$|[_\s0-9])", "phone"),
    (r"(?:^|[_\s])(dob|birth|date)(?:$|[_\s0-9])", "date"),
    (r"(amount|amt|price|fee|cost|salary|income|naira|ngn|balance)", "numeric"),
    (r"(?:^|[_\s])(sex|gender)(?:$|[_\s])", "gender"),
]


def _header_hint(name: str):
    import re as _re
    h = str(name).lower()
    for pat, typ in _HEADER_HINTS:
        if _re.search(pat, h):
            return typ
    return None


def _is_coordish(s: str) -> bool:
    s = str(s).strip()
    if not s:
        return False
    # reject values carrying words (e.g. "6 - 10 years"): a coordinate has no letters
    # other than direction markers N/S/E/W
    letters = [c for c in s if c.isalpha()]
    if letters and any(c.upper() not in "NSEW" for c in letters):
        return False
    # a bare "6 - 10" is a range, not DMS: DMS uses ° ' " markers
    if "-" in s[1:] and not any(m in s for m in "°'\""):
        return False
    # plain decimal in a plausible coordinate range
    try:
        f = float(s.replace(",", "").strip())
        return -180.0 <= f <= 180.0
    except ValueError:
        pass
    # proper DMS with degree/direction markers
    if any(m in s for m in "°'\"") or (letters and all(c.upper() in "NSEW" for c in letters)):
        try:
            from lat_lon_parser import parse
            float(parse(s)); return True
        except Exception:
            return False
    return False


def _profile_column_rules(series: pd.Series, name: str, gazetteers: dict | None = None,
                   place_index: dict | None = None) -> ColumnProfile:
    vals = _clean_vals(series)
    n = len(vals)
    if n == 0:
        return ColumnProfile(name, "empty", 1.0, None, evidence={"nonnull": 0})

    # header tells us what values alone can't: "lat"/"long" are just decimals
    hint = _header_hint(name)
    if hint in ("latitude", "longitude"):
        if sum(1 for v in vals if _is_coordish(v)) / n >= 0.6:
            return ColumnProfile(name, hint, 0.9, hint, evidence={"header_hint": hint})
    if hint == "geopoint":
        if sum(1 for v in vals if ("," in v or ";" in v) and any(c.isdigit() for c in v)) / n >= 0.6:
            return ColumnProfile(name, "geopoint", 0.9, None, evidence={"header_hint": "geopoint"})

    # 0/1 indicator (select-multiple dummy): leave it alone, don't clutter review
    if set(vals) <= {"0", "1"}:
        return ColumnProfile(name, "indicator", 1.0, None, evidence={"values": "0/1"})

    # timestamp (date + time component) -> datetime, distinct from a plain date
    import re as _re
    _time = _re.compile(r"\d{1,2}:\d{2}")
    _dateish = _re.compile(r"\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}|\d{4}-\d{2}-\d{2}")
    ts_rate = sum(1 for v in vals if _time.search(v) and _dateish.search(v)) / n
    if ts_rate >= 0.7:
        return ColumnProfile(name, "datetime", ts_rate, "datetime_iso", evidence={"timestamp_rate": round(ts_rate, 2)})

    # number carrying a known unit (3200g, 12 kg, 5 ha) -> parse to a number
    _known_units = {"g", "kg", "mg", "lb", "oz", "t", "ha", "m", "cm", "mm", "km",
                    "l", "ml", "hr", "hrs", "hour", "hours", "min", "mins", "sec", "yr", "yrs"}
    _unit_re = _re.compile(r"^[-+]?\d[\d,\.]*\s*([a-zA-Z]{1,5})$")
    def _has_unit(v):
        m = _unit_re.match(v)
        return bool(m) and m.group(1).lower() in _known_units
    unit_rate = sum(1 for v in vals if _has_unit(v)) / n
    if unit_rate >= 0.7:
        return ColumnProfile(name, "numeric", unit_rate, "unit_numeric", evidence={"unit_rate": round(unit_rate, 2)})

    distinct = list(dict.fromkeys(vals))
    d = len(distinct)
    card_ratio = d / n
    avg_len = sum(len(v) for v in vals) / n
    avg_tokens = sum(len(v.split()) for v in vals) / n

    email_rate = _rate(vals, lambda s: bool(_EMAIL.match(s)))
    phone_rate = _rate(vals, lambda s: bool(_PHONE.match(_digits(s) if s[:1] != "+" else s)) or bool(_PHONE.match(s.replace(" ", "").replace("-", ""))))
    digit_rate = _rate(vals, lambda s: bool(_DIGITS.match(_digits(s))) and _digits(s) != "")
    numeric_rate = _rate(vals, lambda s: bool(_NUMERIC.match(re.sub(r"[,$£€₦%\s]", "", s))))
    decimal_rate = _rate(vals, lambda s: bool(re.match(r"^-?\d+\.\d+$", re.sub(r"[,$£€₦%\s]", "", s))))
    # Alphanumeric-only (no dots, slashes, hyphens, spaces): identifies IDs and
    # cleanly EXCLUDES dates (2025-03-14) and decimals (3.45) from being read as IDs.
    alnum_rate = _rate(vals, lambda s: bool(re.match(r"^[A-Za-z0-9]+$", s)) and any(ch.isdigit() for ch in s))
    date_rate = _rate(vals, _date_ok)

    ev = {"n": n, "distinct": d, "card_ratio": round(card_ratio, 3),
          "avg_len": round(avg_len, 1), "avg_tokens": round(avg_tokens, 1),
          "email_rate": round(email_rate, 2), "phone_rate": round(phone_rate, 2),
          "digit_rate": round(digit_rate, 2), "numeric_rate": round(numeric_rate, 2),
          "date_rate": round(date_rate, 2)}

    lower_distinct = {s.lower() for s in distinct}

    # --- ordered inference (most specific first) ---
    if email_rate >= 0.7:
        return ColumnProfile(name, "email", email_rate, "email", evidence=ev)

    if lower_distinct <= _GENDER and d <= 6:
        return ColumnProfile(name, "gender", 0.95, "gender", evidence=ev)

    if lower_distinct <= _BOOL and d <= 4:
        return ColumnProfile(name, "boolean", 0.95, "boolean", evidence=ev)

    if phone_rate >= 0.7:
        return ColumnProfile(name, "phone", phone_rate, "phone_ng", evidence=ev)

    # numeric MEASURE with decimals (e.g. hectares, amounts) -> numeric, before id.
    if numeric_rate >= 0.85 and decimal_rate >= 0.3:
        return ColumnProfile(name, "numeric", numeric_rate, "numeric", evidence=ev)

    # identifier: alphanumeric-only (excludes dates & decimals), has digits,
    # high cardinality, fairly uniform digit length.
    if alnum_rate >= 0.8 and card_ratio >= 0.6:
        lens = [len(_digits(v)) for v in vals if _digits(v)]
        mode_len = max(set(lens), key=lens.count) if lens else 0
        len_consistency = lens.count(mode_len) / len(lens) if lens else 0
        if len_consistency >= 0.6:
            ev["id_length"] = mode_len
            if mode_len == 11:
                # 11-digit national IDs (NIN, and BVN which shares the format).
                return ColumnProfile(name, "identifier", 0.9, "nin", evidence=ev)
            return ColumnProfile(name, "identifier", 0.85, "fixed_id",
                                 params={"length": mode_len}, evidence=ev)

    if date_rate >= 0.8:
        return ColumnProfile(name, "date", date_rate, "date_iso", evidence=ev)

    # geographic: distinct values resolve against state names OR known places
    if gazetteers:
        for geo_name, canonical in gazetteers.items():
            resolver = EntityResolver(canonical)
            places = (place_index or {}).get(geo_name, set())
            hits = sum(1 for v in distinct
                       if _norm_key(v) in places or resolver.resolve(v).band in ("high", "review"))
            hit_rate = hits / d
            if hit_rate >= 0.6:
                ev["geo_match"] = {geo_name: round(hit_rate, 2)}
                return ColumnProfile(name, "geo", hit_rate, "resolve",
                                     params={"gazetteer": geo_name}, evidence=ev)

    # numeric measure (integers)
    if numeric_rate >= 0.85:
        return ColumnProfile(name, "numeric", numeric_rate, "numeric", evidence=ev)

    # person name: 1-3 alphabetic tokens, high cardinality (checked before
    # categorical so real name columns aren't mistaken for small vocabularies).
    alpha_rate = _rate(vals, lambda s: s.replace(" ", "").replace("-", "").replace("'", "").isalpha())
    if alpha_rate >= 0.8 and 1 < avg_tokens <= 3 and card_ratio >= 0.5:
        return ColumnProfile(name, "name", 0.75, "name", evidence=ev)

    # categorical: low distinct count relative to rows, short-ish values
    if (d <= 60 and card_ratio <= 0.5 and avg_tokens <= 4) or (d <= 25 and n >= 20):
        return ColumnProfile(name, "categorical", 0.8, "induce_vocabulary", evidence=ev)

    # single-token alphabetic, higher cardinality -> name fallback
    if alpha_rate >= 0.8 and avg_tokens <= 3 and card_ratio >= 0.5:
        return ColumnProfile(name, "name", 0.7, "name", evidence=ev)

    # otherwise free text
    return ColumnProfile(name, "free_text", 0.6, "text_normalise", evidence=ev)


def profile_column(series: pd.Series, name: str, gazetteers: dict | None = None,
                   place_index: dict | None = None, use_ml: bool = False,
                   use_nlp: bool = False) -> ColumnProfile:
    """Rule-based profiling, optionally rescued by the trained type classifier.

    The rules stay authoritative. When `use_ml` is on and the rules land on a
    soft type (categorical / name / free_text) but the trained model is
    confident the column is a structured type (numeric, date, phone, …), the
    model's call wins — this is what rescues a mostly-numeric column polluted
    with 'Do not know'. If no model is installed, behaviour is unchanged.
    """
    result = _profile_column_rules(series, name, gazetteers, place_index)
    if use_nlp and result.semantic_type in {"categorical", "name", "free_text"}:
        try:
            from .nlp import available as _nlp_ok, column_entity_type
            if _nlp_ok():
                ner_type, ner_conf = column_entity_type(_clean_vals(series))
                _safe = {"numeric", "date", "name", "organization", "place"}
                if ner_type in _safe and ner_conf >= 0.6 and ner_type != result.semantic_type:
                    tf = {"numeric": "numeric", "date": "date_iso", "name": "name"}.get(ner_type)  # org/place -> no-op
                    ev = dict(result.evidence or {}); ev["nlp"] = {ner_type: round(ner_conf, 2)}
                    return ColumnProfile(name, ner_type, ner_conf, tf, evidence=ev)
        except Exception:
            pass
    if not use_ml or result.semantic_type not in {"categorical", "name", "free_text", "identifier"}:
        return result
    try:
        from .ml.predict import predict_detail
    except Exception:
        return result
    vals = _clean_vals(series)
    ml_type, ml_conf, ml_margin = predict_detail(vals)
    rescuable = {"numeric", "date", "datetime", "phone", "email", "boolean", "gender"}
    if result.semantic_type == "identifier":
        rescuable = {"numeric", "date", "datetime", "email", "boolean", "gender"}  # ID vs phone too ambiguous
    strong = ml_conf >= 0.35 and ml_margin >= 0.20
    numeric_ok = ml_type == "numeric" and ml_conf >= 0.30 and ml_margin >= 0.10  # length-guarded below
    if ml_type in rescuable and (strong or numeric_ok) and ml_type != result.semantic_type:
        if ml_type == "numeric":
            import re as _re
            lens = sorted(len(_re.sub(r"\D", "", v)) for v in vals if any(c.isdigit() for c in v))
            if lens and lens[len(lens) // 2] > 6:      # long digit strings are IDs, not measures
                return result
        transform = _TYPE_TO_TRANSFORM.get(ml_type, ("text_normalise", {}))[0]
        ev = dict(result.evidence or {}); ev["ml_assist"] = {ml_type: round(ml_conf, 2)}
        return ColumnProfile(name, ml_type, ml_conf, transform, evidence=ev)
    return result


def profile_dataframe(df: pd.DataFrame, gazetteers: dict | None = None,
                      place_index: dict | None = None, use_ml: bool = False, use_nlp: bool = False) -> list[ColumnProfile]:
    return [profile_column(df[c], c, gazetteers, place_index, use_ml, use_nlp) for c in df.columns]


# --- turn profiles into an executable, review-ready plan -------------------
_TYPE_TO_TRANSFORM = {
    "email": ("email", {}),
    "gender": ("gender", {}),
    "boolean": ("boolean", {}),
    "phone": ("phone_ng", {}),
    "date": ("date_iso", {}),
    "datetime": ("datetime_iso", {}),
    "numeric": ("numeric", {}),
    "latitude": ("latitude", {}),
    "longitude": ("longitude", {}),
    "name": ("name", {}),
    "categorical": ("auto_categorical", {}),
    "free_text": ("text_normalise", {}),
}


def profile_to_plan(profiles: list[ColumnProfile], plan_name: str = "auto",
                    gazetteer_refs: dict | None = None) -> dict:
    """Build a proposed cleaning plan from column profiles. Works on ANY file:
    the plan is derived from inferred types, not a known schema. Geographic
    columns point at whichever gazetteer reference file the caller supplies."""
    gazetteer_refs = gazetteer_refs or {}
    mappings = []
    for p in profiles:
        if p.semantic_type in ("indicator", "empty", "geopoint", "organization", "place"):
            continue
        if p.semantic_type == "identifier":
            transform = p.transform  # 'nin' or 'fixed_id'
            params = dict(p.params)
        elif p.semantic_type == "geo":
            gaz = p.params.get("gazetteer")
            ref = gazetteer_refs.get(gaz)
            transform, params = ("resolve", {"reference": ref} if ref else {})
        else:
            transform, params = _TYPE_TO_TRANSFORM.get(p.semantic_type, (None, {}))
        mappings.append({
            "source_column": p.column,
            "target_field": p.column,
            "transform": transform,
            "params": params,
            "inferred_type": p.semantic_type,
            "confidence": round(p.confidence, 2),
        })
    return {"name": plan_name, "generated_by": "data profiler (types inferred from values)",
            "mappings": mappings}

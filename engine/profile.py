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


def _re_fullmatch_serial(s):
    return bool(re.fullmatch(r"\d{5}(?:\.\d+)?", str(s).strip()))


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

    letter_share = _rate(vals, lambda s: any(ch.isalpha() for ch in s))
    if phone_rate >= 0.7 and letter_share < 0.1:      # phones never contain letters
        return ColumnProfile(name, "phone", phone_rate, "phone_ng", evidence=ev)

    # a column of bare Excel date-serials (e.g. 44197, 44562) reads as an ID column,
    # but if the header hints a date it is almost certainly leaked dates. Convert
    # only with that hint, so real 5-digit ID/code columns are never corrupted.
    serials = [v for v in vals if _re_fullmatch_serial(v)]
    if serials and len(serials) / len(vals) >= 0.9:
        hint = any(k in name.lower() for k in
                   ("date", "day", "created", "closed", "resolved", "time",
                    "dob", "birth", "start", "end", "period", "month", "year", "timestamp"))
        if hint:
            ev["excel_date_serials"] = True
            return ColumnProfile(name, "date", 0.85, "date_iso", evidence=ev)

    # leading-zero digit strings are codes (IDs, ZIP, account nos), never measures:
    # "007" is not the number 7. Keep them as identifiers so zeros are preserved.
    pure_digits = [v for v in vals if v.isdigit()]
    if pure_digits and len(pure_digits) / len(vals) >= 0.8:
        lead_zero = [v for v in pure_digits if len(v) > 1 and v[0] == "0"]
        if len(lead_zero) / len(pure_digits) >= 0.3:
            lens = [len(v) for v in pure_digits]
            mode_len = max(set(lens), key=lens.count)
            ev["leading_zeros"] = True
            return ColumnProfile(name, "identifier", 0.9, "fixed_id",
                                 params={"length": mode_len}, evidence=ev)

    # mixed digit + alphanumeric codes (e.g. account nos "1234567890" alongside
    # "ABC123") are identifiers, never phones or measures.
    if letter_share >= 0.15 and alnum_rate >= 0.85 and numeric_rate < 0.85 and date_rate < 0.5:
        ev["alphanumeric_codes"] = round(letter_share, 2)
        return ColumnProfile(name, "identifier", 0.8, "fixed_id", evidence=ev)

    # numeric MEASURE with decimals (e.g. hectares, amounts) -> numeric, before id.
    if numeric_rate >= 0.85 and decimal_rate >= 0.3:
        conv, conv_ev = infer_decimal_convention(vals)
        ev["decimal_convention"] = conv
        return ColumnProfile(name, "numeric", numeric_rate, "numeric",
                             params={"decimal": conv}, evidence=ev)

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
        order, order_ev = infer_date_order(vals)
        ev["date_order"] = order or "ambiguous"
        ev["date_order_evidence"] = order_ev
        params = {"date_order": order} if order else {}
        return ColumnProfile(name, "date", date_rate, "date_iso", params=params, evidence=ev)

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

    # spread numeric measure with some junk (e.g. age with 'forty'/'-4'/sentinels):
    # if numbers dominate and the numeric values are varied, treat as numeric and
    # let the pipeline flag the non-numeric values rather than call it a category.
    def _isnum(s):
        try:
            float(str(s).replace(",", "")); return True
        except ValueError:
            return False
    num_distinct = len({v for v in vals if _isnum(v)})
    if numeric_rate >= 0.55 and num_distinct >= 6 and decimal_rate < 0.3:
        conv, _cev = infer_decimal_convention(vals)
        ev["decimal_convention"] = conv
        ev["mixed_numeric"] = True
        return ColumnProfile(name, "numeric", numeric_rate, "numeric",
                             params={"decimal": conv}, evidence=ev)

    # numeric measure (integers)
    if numeric_rate >= 0.85:
        conv, conv_ev = infer_decimal_convention(vals)
        ev["decimal_convention"] = conv
        return ColumnProfile(name, "numeric", numeric_rate, "numeric",
                             params={"decimal": conv}, evidence=ev)

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


def infer_decimal_convention(values, min_share: float = 0.51) -> tuple[str, dict]:
    """Decide a column's decimal convention from the whole column.

    Defaults to 'dot' (dot = decimal, comma = thousands) which fits most English
    and Nigerian data, so 42.959 stays 42.959. Switches to 'comma' (European:
    comma = decimal, dot = thousands) only with positive evidence:
      * values carrying BOTH separators where the comma is the rightmost, or
      * comma-only values where a majority use comma + 1-2 trailing digits (12,5)
    Returns ('dot' | 'comma', evidence).
    """
    import re as _r
    dot_dec = comma_dec = 0
    comma_2 = comma_3 = comma_only = 0
    for v in values:
        s = _r.sub(r"[^0-9.,]", "", str(v))
        if not s:
            continue
        has_c, has_d = "," in s, "." in s
        if has_c and has_d:
            if s.rfind(",") > s.rfind("."):
                comma_dec += 1
            else:
                dot_dec += 1
        elif has_c:
            comma_only += 1
            tail = s.split(",")[-1]
            if len(tail) in (1, 2):
                comma_2 += 1
            elif len(tail) == 3:
                comma_3 += 1
    if comma_dec + dot_dec > 0:
        conv = "comma" if comma_dec > dot_dec else "dot"
        return conv, {"both_sep": comma_dec + dot_dec, "comma_decimal": comma_dec, "dot_decimal": dot_dec}
    if comma_only > 0 and comma_2 / comma_only >= min_share and comma_2 >= 3:
        return "comma", {"comma_only": comma_only, "comma_2digit": comma_2}
    return "dot", {"default": True}


def infer_date_order(values, min_share: float = 0.51) -> tuple[str | None, dict]:
    """Decide day/month order for a whole column by MAJORITY (>=51%), so one
    stray/typo value cannot flip the format.

    For 3-part numeric dates (d1 SEP d2 SEP d3):
      * 4-digit first component in the majority  -> 'YMD'
      * else assume year last; whichever of the first/middle component exceeds 12
        in a majority of rows is the DAY:
          - first  > 12 majority -> 'DMY' (day first)
          - middle > 12 majority -> 'MDY' (month first, day in the middle)
      * neither reaches the majority -> None (genuinely ambiguous; ask the user)
    Returns (order or None, evidence).
    """
    import re as _r
    pat = _r.compile(r"^\s*(\d{1,4})[./-](\d{1,2})[./-](\d{1,4})\s*$")
    parts = []
    for v in values:
        m = pat.match(str(v).strip())
        if m:
            a, b, c = (int(x) for x in m.groups())
            parts.append((a, b, len(m.group(1)) == 4, len(m.group(3)) == 4))
    n = len(parts)
    if n == 0:
        return None, {"dateable": 0}
    first_year = sum(1 for p in parts if p[2]) / n
    if first_year >= min_share:
        return "YMD", {"dateable": n, "reason": "4-digit year first", "share": round(first_year, 2)}
    d1_gt12 = sum(1 for p in parts if p[0] > 12) / n
    d2_gt12 = sum(1 for p in parts if p[1] > 12) / n
    if d1_gt12 >= min_share:
        return "DMY", {"dateable": n, "first_gt12": round(d1_gt12, 2)}
    if d2_gt12 >= min_share:
        return "MDY", {"dateable": n, "middle_gt12": round(d2_gt12, 2)}
    return None, {"dateable": n, "ambiguous": True,
                  "first_gt12": round(d1_gt12, 2), "middle_gt12": round(d2_gt12, 2)}


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
            transform, base_params = _TYPE_TO_TRANSFORM.get(p.semantic_type, (None, {}))
            params = {**base_params, **(p.params or {})}   # carry inferred params (e.g. date_order)
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

"""Turn a column of values into numeric features for the type classifier.

Features describe the *shape* of a column, not its content, so the model
generalises across countries and sectors: what fraction parse as numbers, as
dates, as booleans; how many distinct values; average token count and length;
how much looks like an email/phone/id. No text is memorised.
"""
from __future__ import annotations

import re
from statistics import mean

_NUM = re.compile(r"^[\s]*[-(]?[\d][\d,\.\s]*%?\)?\s*$")
_EMAILish = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONEish = re.compile(r"^[\s+()\-\d]{7,}$")
_ALNUM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-/]{2,}$")
_DATEish = re.compile(r"\d{1,4}[/\-.]\d{1,2}([/\-.]\d{1,4})?|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\b", re.I)
_TIMEish = re.compile(r"\d{1,2}:\d{2}(:\d{2})?")     # a time component -> timestamp
_BOOL = {"yes", "no", "y", "n", "true", "false", "1", "0"}
_GENDER = {"m", "f", "male", "female", "man", "woman", "boy", "girl"}


def _num_frac(vals):
    def isnum(s):
        t = re.sub(r"[,%$₦£€\s()]", "", s)
        try:
            float(t); return True
        except ValueError:
            return False
    return mean([1.0 if isnum(v) else 0.0 for v in vals]) if vals else 0.0


def column_features(values) -> list[float]:
    vals = [str(v).strip() for v in values if str(v).strip() != ""]
    n = len(vals)
    if n == 0:
        return [0.0] * 12
    distinct = len(set(vals))
    low = [v.lower() for v in vals]
    def frac(pred): return sum(1 for v in vals if pred(v)) / n
    return [
        _num_frac(vals),                                        # numeric-looking
        frac(lambda v: bool(_DATEish.search(v))),               # date-looking
        sum(1 for v in low if v in _BOOL) / n,                  # boolean
        sum(1 for v in low if v in _GENDER) / n,                # gender
        frac(lambda v: bool(_EMAILish.match(v))),               # email
        frac(lambda v: bool(_PHONEish.match(v)) and sum(c.isdigit() for c in v) >= 7),  # phone
        frac(lambda v: bool(_ALNUM_ID.match(v)) and any(c.isdigit() for c in v)),       # id-like
        distinct / n,                                           # distinct ratio
        min(1.0, mean(len(v.split()) for v in vals) / 6),       # avg tokens (norm)
        min(1.0, mean(len(v) for v in vals) / 40),              # avg length (norm)
        frac(lambda v: " " in v),                               # has spaces (names/text)
        min(1.0, distinct / 25),                                # cardinality (norm)
        1.0 if set(vals) <= {"0", "1"} else 0.0,                # 0/1 indicator (dummy)
        frac(lambda v: bool(_TIMEish.search(v))),               # has a time component (timestamp)
    ]


FEATURE_NAMES = ["num", "date", "bool", "gender", "email", "phone", "id",
                 "distinct_ratio", "avg_tokens", "avg_len", "has_space", "cardinality",
                 "is_01", "has_time"]

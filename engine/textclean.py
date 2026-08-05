"""Natural-language / free-text robustness.

Free-text columns (addresses, remarks, names typed by hand) carry the worst
mess: broken encodings (mojibake), zero-width characters, smart quotes, doubled
spaces, and a dozen ways of writing "missing". This module normalises all of
that deterministically, detects the language of a column, and can pull
structured values (emails, phones, dates) out of prose.

Deterministic and local. Heavier NLP (named-entity recognition, semantic
parsing) needs a model and is the optional AI layer, not this module.
"""
from __future__ import annotations

import re
import unicodedata

# things people write to mean "no value"
_NA_TOKENS = {"", "na", "n/a", "n.a.", "#n/a", "nan", "null", "none", "nil",
             "-", "--", "---", ".", "?", "unknown", "unk", "not available",
             "not applicable", "no data", "tbd", "tba", "xxx", "n\\a"}

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff\u2060"), None)
_QUOTES = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
           "\u2032": "'", "\u2033": '"'}
_DASHES = {"\u2013": "-", "\u2014": "-", "\u2212": "-"}
_WS = re.compile(r"\s+")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?:\+?234|0)\d[\d\s\-]{7,}\d")
_DATE = re.compile(r"\b(\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4})\b")
_LONGNUM = re.compile(r"\b\d{10,11}\b")   # NIN/BVN-like


def normalize_text(value) -> str:
    """Repair encoding, strip invisible characters, normalise quotes/dashes and
    whitespace. Safe to run on any text; never changes meaning."""
    if value is None:
        return ""
    s = str(value)
    try:
        import ftfy
        s = ftfy.fix_text(s)                      # repair mojibake (Ã© -> é, etc.)
    except Exception:
        pass
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_ZERO_WIDTH)
    s = _CTRL.sub(" ", s)
    for a, b in {**_QUOTES, **_DASHES}.items():
        s = s.replace(a, b)
    return _WS.sub(" ", s).strip()


def normalize_missing(value):
    """Return '' for any of the many 'missing' spellings, else the value."""
    s = normalize_text(value)
    return "" if s.lower() in _NA_TOKENS else s


def detect_language(values, sample: int = 60) -> str | None:
    """Best-effort language of a column, from a sample of its values."""
    try:
        from langdetect import detect, DetectorFactory
        DetectorFactory.seed = 0
    except Exception:
        return None
    text = " ".join(str(v) for v in list(values)[:sample] if str(v).strip())
    text = normalize_text(text)
    if len(text) < 12:
        return None
    try:
        return detect(text)
    except Exception:
        return None


def extract(kind: str, text) -> list[str]:
    """Pull structured values out of free text. kind in
    {email, phone, date, longnum}."""
    s = normalize_text(text)
    pat = {"email": _EMAIL, "phone": _PHONE, "date": _DATE, "longnum": _LONGNUM}[kind]
    seen, out = set(), []
    for m in pat.findall(s):
        v = m[0] if isinstance(m, tuple) else m
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out

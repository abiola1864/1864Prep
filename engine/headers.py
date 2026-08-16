"""Column-name (header) normalisation.

Real cleaning fixes the structure before the values: if a column is blank,
cryptic ("Var2"), a leaked date-serial, or machine-cased ("date_of_birth"),
everything downstream reads strangely. This module proposes a good, readable
name for every column, inferring one from the column's contents when the header
itself is missing or generic. Proposals are surfaced for approval; nothing is
renamed without consent.

No dataset-specific names are baked in here. Reference labels (State, LGA,
Country, ...) come from the detected domain, which is official reference data.
"""
from __future__ import annotations

import re

# headers that carry no real meaning and should be named from content instead
_NOHEADER = re.compile(r"^column_\d+_no_header$", re.I)
_GENERIC = re.compile(r"^(?:column|col|field|var|variable|unnamed|feature|attr|attribute|x|v|c|f|q)[\s_\-]?\d*$", re.I)
_ISODATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_JUNK = re.compile(r"[\ufffd]")                       # broken/replacement chars

# small, safe, generic abbreviation expansions (no domain-specific guesses)
_EXPAND = {
    "dob": "Date of Birth", "addr": "Address", "qty": "Quantity", "amt": "Amount",
    "tel": "Telephone", "no": "Number", "num": "Number", "yr": "Year",
    "mnth": "Month", "desc": "Description", "avg": "Average",
}
# tokens kept upper-case when they look like acronyms
_ACRONYM = re.compile(r"^[A-Z0-9]{2,5}$")

# how a detected domain / semantic type reads as a human column name
_DOMAIN_LABEL = {
    "ng_state": "State", "ng_lga": "LGA", "subdivision": "Region",
    "country": "Country", "currency": "Currency", "sex": "Gender",
}
_TYPE_LABEL = {
    "date": "Date", "datetime": "Date and Time", "email": "Email Address",
    "phone": "Phone Number", "identifier": "ID", "numeric": "Value",
    "boolean": "Yes/No", "name": "Name", "geo": "Location", "coordinate": "Coordinates",
    "currency": "Amount", "categorical": "Category", "free_text": "Text",
}


def is_abnormal(name: str) -> tuple[bool, str]:
    """Return (abnormal, reason) for a header that a person would find strange."""
    s = "" if name is None else str(name).strip()
    if not s:
        return True, "blank"
    if _NOHEADER.match(s):
        return True, "no header in the file"
    if _GENERIC.match(s):
        return True, "a generic placeholder"
    if _ISODATE.match(s):
        return True, "a date used as a header"
    if _JUNK.search(s):
        return True, "contains broken characters"
    if len(s) > 60:
        return True, "unusually long"
    if re.fullmatch(r"[\W_]+", s):
        return True, "only symbols"
    return False, ""


def readable(name: str) -> str:
    """Turn a machine-style header into a readable one.
    date_of_birth -> Date of Birth ; customerID -> Customer ID ; lga-code -> LGA Code
    """
    s = str(name).strip()
    s = re.sub(r"[_\-\.]+", " ", s)                       # separators -> space
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)         # camelCase -> two words
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", s)       # HTTPServer -> HTTP Server
    s = re.sub(r"\s+", " ", s).strip()
    out = []
    small = {"of", "the", "a", "an", "and", "or", "to", "in", "for", "by"}
    for i, tok in enumerate(s.split(" ")):
        low = tok.lower()
        if low in _EXPAND:
            out.append(_EXPAND[low])
        elif _ACRONYM.match(tok):                          # keep ID, LGA, NIN as-is
            out.append(tok.upper())
        elif i > 0 and low in small:
            out.append(low)
        else:
            out.append(tok[:1].upper() + tok[1:].lower() if tok else tok)
    return " ".join(out).strip()


def _from_content(profile, domain: str | None) -> str | None:
    """Name a blank/generic column from what it actually holds."""
    if domain and domain in _DOMAIN_LABEL:
        return _DOMAIN_LABEL[domain]
    st = getattr(profile, "semantic_type", None) if profile is not None else None
    return _TYPE_LABEL.get(st)


def _uniquify(names: list[str]) -> list[str]:
    seen, out = {}, []
    for n in names:
        if n in seen:
            seen[n] += 1
            out.append(f"{n} {seen[n]}")
        else:
            seen[n] = 1
            out.append(n)
    return out


def propose_headers(df, profiles=None, domains=None) -> list[dict]:
    """Propose a clean name for every column.

    Returns one dict per column:
      {original, suggested, abnormal, reason}
    Abnormal columns (blank, generic, leaked serials) are named from their
    content; the rest get a readable version of the existing header. Suggested
    names are made unique. The caller can present abnormal columns first.
    """
    cols = list(df.columns)
    profiles = profiles or [None] * len(cols)
    domains = domains or [None] * len(cols)
    raw_suggestions, rows = [], []
    for i, col in enumerate(cols):
        abnormal, reason = is_abnormal(col)
        prof = profiles[i] if i < len(profiles) else None
        dom = domains[i] if i < len(domains) else None
        if abnormal:
            guess = _from_content(prof, dom) or "Column"
        else:
            guess = readable(col)
        raw_suggestions.append(guess)
        rows.append({"original": str(col), "abnormal": abnormal, "reason": reason})
    unique = _uniquify(raw_suggestions)
    for r, sug in zip(rows, unique):
        r["suggested"] = sug
    return rows


def abnormal_count(rows: list[dict]) -> int:
    return sum(1 for r in rows if r.get("abnormal"))

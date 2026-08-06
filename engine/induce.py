"""Vocabulary induction: collapse the SAME category written differently into one
standard label — without ever merging categories that actually differ.

Two hard rules, learned from real failures:

  1. Numbers carry meaning. Values whose numeric content differs are NEVER
     merged. "6-10 years" and "21-25 years" stay separate no matter how similar
     the surrounding words are.
  2. Merge only same-meaning variants. Case, punctuation, spacing, '&' vs 'and',
     and word order are cosmetic -> merge. Different WORDS are a different
     category -> keep distinct (borderline cases are left separate, never guessed).

So "Drinks, Water, Wine & Spirits" and "drinks, water, wine and spirits" collapse
to one; "Provisions" and "Groceries" do not.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

_AMP = re.compile(r"\s*&\s*|\s+and\s+", re.I)
_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")
_NUM = re.compile(r"\d+")


def _numbers(s: str) -> tuple:
    """The sequence of numbers in a value — its meaning-bearing fingerprint."""
    return tuple(int(n) for n in _NUM.findall(s))


def _canonical_key(s: str) -> str:
    """Meaning-preserving key: same key == genuinely the same category.
    Lower-case, '&'/'and' unified, punctuation dropped, words sorted, numbers
    kept verbatim so ranges never collapse together."""
    s = str(s).strip().lower()
    s = _AMP.sub(" and ", s)
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    if not s:
        return ""
    nums = _numbers(s)
    words = sorted(w for w in s.split() if not w.isdigit())
    return "|".join(words) + "#" + ",".join(map(str, nums))


def _titlecase(s: str) -> str:
    s = _WS.sub(" ", str(s).strip())
    # standardise ' and ' -> ' & ' for display, Title-Case words
    out = []
    for w in s.split():
        if w.lower() in {"and"}:
            out.append("&")
        elif w.isupper() and len(w) <= 4:
            out.append(w)                     # keep acronyms (NGO, ICT)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


@dataclass
class InducedVocab:
    mapping: dict          # raw value -> standard label
    clusters: dict = field(default_factory=dict)   # label -> member spellings
    n_raw: int = 0
    n_canonical: int = 0


def induce_vocabulary(values, threshold: float = 0.86) -> InducedVocab:
    """Group values that are the SAME category written differently.

    `threshold` is kept for API compatibility but exact same-meaning keying is
    used (no fuzzy merging across different words/numbers), because that is what
    makes the result safe. Fuzzy *suggestions* for genuinely different spellings
    live in engine/dedupe.group_similar, which only proposes — never applies.
    """
    counts = Counter(str(v).strip() for v in values if str(v).strip())
    groups: dict[str, list[str]] = {}
    for value in counts:
        key = _canonical_key(value)
        if key == "":
            continue
        groups.setdefault(key, []).append(value)

    mapping, clusters = {}, {}
    for members in groups.values():
        # label = the most frequent spelling, tidied for display
        rep = sorted(members, key=lambda m: (counts[m], len(m)), reverse=True)[0]
        label = _titlecase(rep)
        clusters[label] = sorted(members, key=lambda m: counts[m], reverse=True)
        for m in members:
            mapping[m] = label

    return InducedVocab(mapping=mapping, clusters=clusters,
                        n_raw=len(counts), n_canonical=len(clusters))

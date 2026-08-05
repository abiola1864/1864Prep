"""Robust entity resolution against an authoritative canonical list.

The point of this module is that it needs ONLY the ground-truth list (the 37
official states, the official LGAs, the licensed operators). It does not need a
hand-maintained dictionary of misspellings. Messy inputs are matched with a
blend of fuzzy string similarity and phonetic similarity, so spellings that were
never enumerated anywhere still resolve.

Why this is safe as well as robust:
  * It is DETERMINISTIC -- the same input always yields the same output and
    score, so a run is repeatable and auditable (unlike letting an LLM rewrite
    values freely).
  * It runs on the SET OF DISTINCT VALUES, not on rows. A register of 18,000
    rows has maybe 200 distinct state strings; we resolve those 200 and apply
    the mapping locally. Nothing per-row, nothing identifying, ever leaves.
  * It abstains. Anything below the review threshold is returned as unresolved
    and flagged, never silently guessed. Low-confidence cases go to the human
    queue (or, as a higher rung, a gazetteer or local model).

Rungs above this module (documented, not all built here):
  * a GAZETTEER (official city/LGA -> state hierarchy) for place->admin mapping,
    which string similarity cannot do ("Port Harcourt" -> Rivers);
  * embedding similarity and a local LLM for genuinely ambiguous residuals.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import jellyfish
from rapidfuzz import fuzz

_PUNCT = re.compile(r"[^a-z0-9\s]")
_WS = re.compile(r"\s+")


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = _PUNCT.sub(" ", s)
    return _WS.sub(" ", s).strip()


def _phonetic_sim(a: str, b: str) -> float:
    """Graded phonetic similarity: Jaro-Winkler over Metaphone codes, blended
    with a Match-Rating-Codex agreement. Robust to consonant transpositions and
    vowel noise common in Nigerian place/name spellings."""
    ma, mb = jellyfish.metaphone(a), jellyfish.metaphone(b)
    if not ma or not mb:
        return 0.0
    jw = jellyfish.jaro_winkler_similarity(ma, mb)
    try:
        mra = jellyfish.match_rating_codex(a.replace(" ", ""))
        mrb = jellyfish.match_rating_codex(b.replace(" ", ""))
        mr = jellyfish.jaro_winkler_similarity(mra, mrb)
    except Exception:
        mr = jw
    return 0.6 * jw + 0.4 * mr


@dataclass
class Match:
    value: str
    canonical: str | None
    score: float
    method: str
    band: str                      # 'high' | 'review' | 'unresolved'
    alternatives: list[tuple[str, float]]


class EntityResolver:
    """Resolve messy values to a canonical list using fuzzy + phonetic signals.

    thresholds: (auto_accept, review) as fractions of 1.0.
    weights:    (fuzzy_weight, phonetic_weight), summing to 1.
    """

    def __init__(self, canonical: list[str], auto_accept: float = 0.88,
                 review: float = 0.72, fuzzy_weight: float = 0.6,
                 memory: dict | None = None):
        self.canonical = list(dict.fromkeys(canonical))
        self.memory = {normalize(k).replace(" ", ""): v for k, v in (memory or {}).items()}
        self._norm = {c: normalize(c) for c in self.canonical}
        self.auto_accept = auto_accept
        self.review = review
        self.fw = fuzzy_weight
        self.pw = 1.0 - fuzzy_weight

    def _score(self, q: str, cnorm: str) -> float:
        fuzzy = max(
            fuzz.token_sort_ratio(q, cnorm),
            fuzz.token_set_ratio(q, cnorm),
            fuzz.WRatio(q, cnorm),
        ) / 100.0
        phon = _phonetic_sim(q, cnorm)
        return self.fw * fuzzy + self.pw * phon

    def resolve(self, value: str) -> Match:
        q = normalize(value)
        if q == "":
            return Match(value, None, 0.0, "empty", "unresolved", [])

        # Learned corrections win outright -- a confirmed mistake is a certainty.
        mem_key = q.replace(" ", "")
        if mem_key in self.memory:
            c = self.memory[mem_key]
            return Match(value, c, 1.0, "learned", "high", [(c, 1.0)])

        # Exact (normalised) match short-circuits with full confidence.
        for c, cn in self._norm.items():
            if q == cn:
                return Match(value, c, 1.0, "exact", "high", [(c, 1.0)])

        scored = sorted(
            ((c, self._score(q, cn)) for c, cn in self._norm.items()),
            key=lambda kv: kv[1], reverse=True,
        )
        best, best_score = scored[0]
        alts = scored[:3]

        if best_score >= self.auto_accept:
            band, method = "high", "fuzzy+phonetic"
        elif best_score >= self.review:
            band, method = "review", "fuzzy+phonetic"
        else:
            return Match(value, None, best_score, "fuzzy+phonetic", "unresolved", alts)
        return Match(value, best, best_score, method, band, alts)

    def resolve_distinct(self, values) -> dict[str, Match]:
        """Resolve the SET of distinct values once; caller applies to all rows.
        This is the privacy-preserving unit of work."""
        distinct = sorted({normalize(v): v for v in values if normalize(v)}.values())
        return {v: self.resolve(v) for v in distinct}

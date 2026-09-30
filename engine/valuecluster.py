"""Instant, offline value clustering: group variant spellings of the same value
(case/whitespace/punctuation differences and near-typos) with no AI and no network.
This is what "AI value cleaning" was doing slowly; fuzzy matching does it in
milliseconds and works fully local. AI stays as a rare, optional fallback.
"""
from __future__ import annotations
import re

try:
    from rapidfuzz import fuzz
    def _sim(a, b): return fuzz.ratio(a, b) / 100.0
except Exception:
    from difflib import SequenceMatcher
    def _sim(a, b): return SequenceMatcher(None, a, b).ratio()


def _norm(s):
    s = str(s).strip().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def cluster_values(values, threshold: float = 0.88, max_distinct: int = 400) -> dict:
    """Return {canonical: [variants...]} for groups that have a real duplicate.
    Canonical = the most frequent original spelling in the group."""
    from collections import Counter
    counts = Counter(str(v).strip() for v in values if str(v).strip())
    distinct = list(counts.keys())[:max_distinct]
    if len(distinct) < 3:
        return {}
    norms = {d: _norm(d) for d in distinct}
    used = set(); groups = []
    # exact-normalised groups first (case/space/punct variants) — instant
    by_norm = {}
    for d in distinct:
        by_norm.setdefault(norms[d], []).append(d)
    for n, members in by_norm.items():
        if len(members) > 1:
            groups.append(members); used.update(members)
    # then near-typo groups among the remainder
    rest = [d for d in distinct if d not in used]
    for i, a in enumerate(rest):
        if a in used:
            continue
        grp = [a]
        for b in rest[i + 1:]:
            if b in used:
                continue
            if _sim(norms[a], norms[b]) >= threshold:
                grp.append(b); used.add(b)
        if len(grp) > 1:
            used.add(a); groups.append(grp)
    out = {}
    for grp in groups:
        canonical = max(grp, key=lambda x: (counts[x], -len(x)))  # most frequent, shortest tiebreak
        variants = [g for g in grp if g != canonical]
        if variants:
            out[canonical] = variants
    return out

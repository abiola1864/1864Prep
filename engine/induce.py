"""Vocabulary induction: build a clean categorical set from messy values, with
NO reference list.

This is the generalisation of the resolver. The resolver maps to a canonical
list you already have (37 states). But a health agency's 'diagnosis', an agric
agency's 'crop', a pension file's 'employer' -- these have a small true
vocabulary that nobody has written down. This module discovers it: it clusters
the distinct values by combined fuzzy + phonetic similarity, so that spelling
variants of the same underlying category collapse together, and proposes a
representative (the most frequent spelling) as the standard.

The human confirms or edits the induced vocabulary in the review step; their
edits become training signal. Works on ANY categorical field in ANY sector
because it reads the data, not a schema.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .resolve import _phonetic_sim, normalize


@dataclass
class InducedVocab:
    mapping: dict[str, str]                    # raw value -> induced canonical
    clusters: dict[str, list[str]] = field(default_factory=dict)  # canonical -> members
    n_raw: int = 0
    n_canonical: int = 0


def _similar(a: str, b: str, fuzzy_weight: float = 0.6) -> float:
    na, nb = normalize(a), normalize(b)
    fuzzy = max(fuzz.token_sort_ratio(na, nb), fuzz.token_set_ratio(na, nb),
                fuzz.WRatio(na, nb)) / 100.0
    return fuzzy_weight * fuzzy + (1 - fuzzy_weight) * _phonetic_sim(na, nb)


class _UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def induce_vocabulary(values, threshold: float = 0.86) -> InducedVocab:
    """Cluster distinct values by similarity; representative = most frequent."""
    counts = Counter(str(v).strip() for v in values if str(v).strip() and normalize(v))
    distinct = list(counts.keys())
    uf = _UnionFind(distinct)

    # O(d^2) over distinct values (usually a few hundred at most).
    for i in range(len(distinct)):
        for j in range(i + 1, len(distinct)):
            if _similar(distinct[i], distinct[j]) >= threshold:
                uf.union(distinct[i], distinct[j])

    groups: dict[str, list[str]] = {}
    for v in distinct:
        groups.setdefault(uf.find(v), []).append(v)

    mapping: dict[str, str] = {}
    clusters: dict[str, list[str]] = {}
    for members in groups.values():
        # Representative: most frequent spelling; ties broken by longer string.
        rep = sorted(members, key=lambda m: (counts[m], len(m)), reverse=True)[0]
        rep_canon = rep.strip().title() if not rep.isupper() else rep.strip()
        clusters[rep_canon] = sorted(members, key=lambda m: counts[m], reverse=True)
        for m in members:
            mapping[m] = rep_canon

    return InducedVocab(mapping=mapping, clusters=clusters,
                        n_raw=len(distinct), n_canonical=len(clusters))

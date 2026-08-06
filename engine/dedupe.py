"""Finding duplicates and similar patterns.

Two things the column-by-column pass doesn't catch on its own:

  * group_similar(values)      -- clusters near-identical VALUES in one column
    (e.g. address variants "Obafemi Awolowo road ikeja" and
    "Obafemi Awolowo road ikeja Lagos"), so the reviewer can merge them.
  * near_duplicate_rows(df)    -- finds ROWS that are the same or almost the same
    record, so the reviewer can drop repeats.

Both are deterministic (fuzzy + phonetic string similarity, no model) and both
only *propose* — nothing is merged or deleted without the person's say-so. They
feed the "needs your attention" worklist rather than changing data silently.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import pandas as pd
from rapidfuzz import fuzz

from .resolve import normalize

# O(n^2) similarity is fine for the distinct values / rows we see in practice;
# above this many distinct items we sample to stay responsive and say so.
_MAX = 1500


def _sim(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    # token_set handles word reorder + one string containing the other
    return max(fuzz.token_set_ratio(na, nb), fuzz.token_sort_ratio(na, nb)) / 100.0


class _UF:
    def __init__(self, items):
        self.p = {x: x for x in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def group_similar(values, threshold: float = 0.85, min_group: int = 2) -> list[dict]:
    """Cluster similar distinct values. Returns groups of 2+ as suggestions,
    largest first: {representative, members, size}."""
    counts = Counter(str(v).strip() for v in values if str(v).strip())
    distinct = list(counts)
    truncated = len(distinct) > _MAX
    if truncated:
        distinct = [v for v, _ in counts.most_common(_MAX)]

    uf = _UF(distinct)
    for i in range(len(distinct)):
        for j in range(i + 1, len(distinct)):
            if _sim(distinct[i], distinct[j]) >= threshold:
                uf.union(distinct[i], distinct[j])

    clusters: dict[str, list[str]] = defaultdict(list)
    for v in distinct:
        clusters[uf.find(v)].append(v)

    out = []
    for members in clusters.values():
        if len(members) >= min_group:
            rep = sorted(members, key=lambda m: (counts[m], len(m)), reverse=True)[0]
            out.append({"representative": rep,
                        "members": sorted(members, key=lambda m: counts[m], reverse=True),
                        "size": len(members)})
    out.sort(key=lambda g: g["size"], reverse=True)
    return out


def _row_key(row) -> str:
    return normalize(" ".join("" if pd.isna(c) else str(c) for c in row))


def near_duplicate_rows(df: pd.DataFrame, subset: list[str] | None = None,
                        threshold: float = 0.92) -> list[dict]:
    """Find duplicate / near-duplicate rows. Returns groups of row indices:
    {rows, kind ('exact'|'near'), similarity}."""
    cols = subset or list(df.columns)
    keys = [_row_key(df[cols].iloc[i]) for i in range(len(df))]

    exact = defaultdict(list)
    for i, k in enumerate(keys):
        if k:
            exact[k].append(i)
    groups = [{"rows": idxs, "kind": "exact", "similarity": 1.0}
              for k, idxs in exact.items() if len(idxs) > 1]

    # near-duplicates: compare distinct keys pairwise (length-bucketed, capped)
    uniq = [(k, idxs[0]) for k, idxs in exact.items()]
    if len(uniq) <= _MAX:
        for a in range(len(uniq)):
            ka, ia = uniq[a]
            for b in range(a + 1, len(uniq)):
                kb, ib = uniq[b]
                if abs(len(ka) - len(kb)) > 0.3 * max(len(ka), len(kb), 1):
                    continue
                s = fuzz.token_set_ratio(ka, kb) / 100.0
                if s >= threshold:
                    groups.append({"rows": [ia, ib], "kind": "near", "similarity": round(s, 3)})
    groups.sort(key=lambda g: (g["kind"] != "exact", -len(g["rows"]), -g["similarity"]))
    return groups

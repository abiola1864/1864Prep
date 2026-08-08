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


# ── graded clustering: propose groups + confidence, never a hard merge ──────────
from itertools import combinations

try:
    from .induce import _numbers            # protect numbers: different numbers never group
except Exception:
    import re as _re
    _numbers = lambda s: tuple(int(n) for n in _re.findall(r"\d+", str(s)))


def _sim_guarded(a: str, b: str) -> float:
    if _numbers(a) != _numbers(b):
        return 0.0
    return _sim(a, b)


def cluster_similar(values, link_threshold: float = 0.72, semantic: bool = False,
                    domain: str | None = None) -> list[dict]:
    """Group values that MIGHT be the same, graded by confidence — no merging.

    Instead of one yes/no cutoff, values are linked when similar, then each
    cluster is scored by how tightly its members hang together:
      * confidence 'high'   — very likely the same (tight variants)
      * 'medium' / 'low'    — possibly the same (looser; for a human to judge)
    Each cluster carries a suggested single name (most frequent, most complete).
    Different numbers never link. If `domain` is given (e.g. 'country'), two
    values that map to DIFFERENT canonical entities are never linked, even if
    they look alike ('Niger' vs 'Nigeria'). Returns clusters of 2+.
    """
    counts = Counter(str(v).strip() for v in values if str(v).strip())
    distinct = list(counts)
    if len(distinct) > _MAX:
        distinct = [v for v, _ in counts.most_common(_MAX)]

    def _blocked(a, b):
        from .induce import _as_number
        na, nb = _as_number(a), _as_number(b)
        if na is not None and nb is not None and na != nb:
            return True                                   # -1 and 1 are different numbers
        if domain:
            try:
                from .domains import same_entity
                if same_entity(domain, a, b) is False:
                    return True
            except Exception:
                pass
        return False

    uf = _UF(distinct)
    for i in range(len(distinct)):
        for j in range(i + 1, len(distinct)):
            if _blocked(distinct[i], distinct[j]):
                continue
            if _sim_guarded(distinct[i], distinct[j]) >= link_threshold:
                uf.union(distinct[i], distinct[j])

    if semantic:
        try:
            from .ml.embed import available, semantic_pairs
            if available():
                for a, b, _s in semantic_pairs(distinct, threshold=0.62):
                    if _numbers(a) == _numbers(b) and not _blocked(a, b):
                        uf.union(a, b)
        except Exception:
            pass

    clusters: dict[str, list[str]] = defaultdict(list)
    for v in distinct:
        clusters[uf.find(v)].append(v)

    out = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        sims = [_sim_guarded(a, b) for a, b in combinations(members, 2)]
        cohesion = min(sims) if sims else 1.0        # weakest link
        avg = sum(sims) / len(sims) if sims else 1.0
        conf = "high" if cohesion >= 0.88 else ("medium" if avg >= 0.80 else "low")
        rep = sorted(members, key=lambda m: (counts[m], len(m)), reverse=True)[0]
        out.append({"representative": rep,
                    "members": sorted(members, key=lambda m: counts[m], reverse=True),
                    "size": len(members),
                    "confidence": conf,
                    "score": round(avg, 3)})
    rank = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda g: (rank[g["confidence"]], -g["size"]))
    return out


def duplicate_columns(df) -> list[dict]:
    """Group columns that are repeats: same header ignoring case/punctuation/the
    pandas '.1' de-dup suffix, or identical cell values. Returns groups of 2+."""
    import re as _re
    def hkey(h):
        h = _re.sub(r"\.\d+$", "", str(h))                 # drop pandas .1/.2 suffix
        return _re.sub(r"[^a-z0-9]+", "", h.lower())
    by_header: dict[str, list[str]] = defaultdict(list)
    for c in df.columns:
        by_header[hkey(c)].append(c)
    groups = []
    for k, cols in by_header.items():
        if len(cols) > 1:
            groups.append({"reason": "same name", "columns": cols})
    return groups

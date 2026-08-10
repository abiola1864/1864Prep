"""Detect duplicate / versioned columns: two or more columns that hold the SAME
field, however their headers are worded (prefixes like RAW_DATA_ / ADRIENNE_, or
a blank header). The reliable signal is VALUE OVERLAP - genuine duplicates carry
the same values row-by-row; a repeating group (capture_1, capture_2, ...) carries
DIFFERENT values and is correctly left alone.

Optional embeddings can sharpen header wording similarity, but identity here rests
on the data, not on names.
"""
from __future__ import annotations

import re

_WS = re.compile(r"\s+")


def _norm_header(h: str) -> str:
    h = re.sub(r"[^a-z0-9 ]+", " ", str(h).lower())
    return _WS.sub(" ", h).strip()


def _value_overlap(a, b) -> float:
    va = a.astype(str).str.strip()
    vb = b.astype(str).str.strip()
    both = (va != "") & (vb != "")
    if not both.any():
        return 0.0
    return float((va[both] == vb[both]).mean())


def find_duplicate_fields(df, overlap: float = 0.75, min_fill: int = 5):
    """Return groups of columns that hold the same field.
    Each group: {"columns": [...], "keep": <suggested column>, "overlap": mean}."""
    cols = [c for c in df.columns if df[c].astype(str).str.strip().ne("").sum() >= min_fill]
    n = len(cols)
    # union-find over columns linked by high value overlap
    parent = {c: c for c in cols}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        parent[find(a)] = find(b)
    pair_ov = {}
    for i in range(n):
        for j in range(i + 1, n):
            ov = _value_overlap(df[cols[i]], df[cols[j]])
            if ov >= overlap:
                pair_ov[(cols[i], cols[j])] = ov
                union(cols[i], cols[j])
    groups = {}
    for c in cols:
        groups.setdefault(find(c), []).append(c)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        # suggest keeping the column with a real header and the most filled values
        def score(c):
            hdr = _norm_header(c)
            has_header = 0 if ("no header" in hdr or not hdr) else 1
            fill = df[c].astype(str).str.strip().ne("").sum()
            return (has_header, fill, -len(str(c)))
        keep = max(members, key=score)
        ovs = [v for (a, b), v in pair_ov.items() if a in members and b in members]
        out.append({"columns": members, "keep": keep,
                    "overlap": round(sum(ovs) / len(ovs), 2) if ovs else 0.0})
    return out

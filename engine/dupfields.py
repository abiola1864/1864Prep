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


_MISS = {"", "..", "...", ":", "-", "--", "na", "n/a", "n.a.", "nan", "null", "none"}
_SEQ = re.compile(r"^((19|20)\d{2}([-_/ ]?(q[1-4]|m?\d{1,2}))?|q[1-4]|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)$", re.I)


def _value_overlap(a, b, min_real: int = 5) -> float:
    va = a.astype(str).str.strip()
    vb = b.astype(str).str.strip()
    ok = ~va.str.lower().isin(_MISS) & ~vb.str.lower().isin(_MISS)
    if ok.sum() < min_real:              # two columns of '..' prove nothing
        return 0.0
    return float((va[ok] == vb[ok]).mean())


def find_duplicate_fields(df, overlap: float = 0.75, min_fill: int = 5):
    """Return groups of columns that hold the same field.
    Each group: {"columns": [...], "keep": <suggested column>, "overlap": mean}."""
    # period columns (1960, 1961, 2020Q1, Jan ...) are different time points by
    # definition, even when they hold the same (or no) values
    cols = [c for c in df.columns
            if not _SEQ.match(str(c).strip())
            and (~df[c].astype(str).str.strip().str.lower().isin(_MISS)).sum() >= min_fill]
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

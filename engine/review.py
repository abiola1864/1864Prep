"""Verification views the user sees BEFORE any cleaning is committed.

Cleaning is only ever a PROPOSAL. Nothing is finalised until the person has seen
what would change and approved it -- you don't alter someone's data into meaning
something else without their consent. Two general views (work on any file):

  1. column_overview  -- every column, before -> after: what type it was read as,
     how many values would change, how many are flagged, with a few real examples.
  2. spotcheck        -- a random sample of actual records, raw beside cleaned,
     so the person can eyeball real rows and confirm they look right.

Both are computed by comparing the original frame to the proposed cleaned frame;
they make no assumptions about columns, sector, or country.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

import pandas as pd


def _s(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v)


@dataclass
class ColumnChange:
    column: str
    read_as: str            # inferred type / transform (human label)
    n_total: int
    n_changed: int
    n_flagged: int
    pct_changed: float
    examples: list[dict] = field(default_factory=list)   # [{before, after}] (small sample)
    changes: list[dict] = field(default_factory=list)     # ALL distinct {before, after, count}


def column_overview(original: pd.DataFrame, cleaned: pd.DataFrame,
                    types: dict | None = None, flags: dict | None = None,
                    max_examples: int = 6, max_changes: int = 800) -> list[dict]:
    types = types or {}
    flags = flags or {}
    out = []
    for col in original.columns:
        if col not in cleaned.columns:
            continue
        before = original[col].map(_s).tolist()
        after = cleaned[col].map(_s).tolist()
        n = len(before)
        changed_pairs, n_changed = [], 0
        distinct = {}                       # (before,after) -> count, every distinct change
        for b, a in zip(before, after):
            if b != a:
                n_changed += 1
                key = (b, a)
                distinct[key] = distinct.get(key, 0) + 1
                if len(changed_pairs) < max_examples and (b or a):
                    if key not in {(c["before"], c["after"]) for c in changed_pairs}:
                        changed_pairs.append({"before": b, "after": a})
        # full distinct-change list, most frequent first, grouped-friendly
        changes = [{"before": b, "after": a, "count": c}
                   for (b, a), c in sorted(distinct.items(), key=lambda kv: kv[1], reverse=True)][:max_changes]
        out.append(asdict(ColumnChange(
            column=col,
            read_as=types.get(col, "—"),
            n_total=n,
            n_changed=n_changed,
            n_flagged=int(flags.get(col, 0)),
            pct_changed=round(100 * n_changed / n, 1) if n else 0.0,
            examples=changed_pairs,
            changes=changes,
        )))
    return out


def spotcheck(original: pd.DataFrame, cleaned: pd.DataFrame,
              pool_size: int = 60, seed: int | None = None) -> dict:
    """Return a pool of random records (raw beside cleaned) for eyeballing.
    The UI shows a handful at a time and can reshuffle from this pool."""
    rng = random.Random(seed)
    cols = [c for c in original.columns if c in cleaned.columns]
    n = len(original)
    idx = list(range(n))
    rng.shuffle(idx)
    idx = idx[:min(pool_size, n)]
    records = []
    for i in idx:
        cells = []
        for c in cols:
            b, a = _s(original[c].iloc[i]), _s(cleaned[c].iloc[i])
            cells.append({"column": c, "before": b, "after": a, "changed": b != a})
        records.append({"row": int(i), "cells": cells})
    return {"columns": cols, "records": records}

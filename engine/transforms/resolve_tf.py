"""Resolver-backed standardisation transform.

Uses EntityResolver (fuzzy + phonetic) against a canonical ground-truth list.
No alias dictionary. Confidence bands mirror the review UI:
  * high        -> output the canonical value (not flagged)
  * review      -> output the proposed canonical value, FLAGGED for confirmation
  * unresolved  -> keep the raw value, FLAGGED with the best guess + score

Efficiency + privacy: resolves the SET of distinct values once, then maps every
row from that lookup. The resolver never sees anything but the distinct strings.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..resolve import EntityResolver
from .base import Change, Transform, TransformResult, _s


class ResolveTransform(Transform):
    """params:
        reference   -- path to a JSON with a 'canonical' list (or 'states' dict).
        auto_accept -- score >= this is accepted automatically (default 0.88).
        review      -- score in [review, auto_accept) is proposed but flagged.
    """
    name = "resolve"

    def __init__(self, **params):
        super().__init__(**params)
        data = json.loads(Path(self.params["reference"]).read_text(encoding="utf-8"))
        if "canonical" in data:
            canonical = data["canonical"]
        elif "states" in data:
            canonical = list(data["states"].keys())
        elif "lgas" in data:
            canonical = [l["canonical"] for l in data["lgas"]]
        else:
            raise ValueError("reference must contain 'canonical', 'states', or 'lgas'")
        self._resolver = EntityResolver(
            canonical,
            auto_accept=float(self.params.get("auto_accept", 0.88)),
            review=float(self.params.get("review", 0.72)),
        )

    def run(self, series: pd.Series, source_column: str, target_field: str) -> TransformResult:
        res = TransformResult(series=series.copy(), source_column=source_column,
                              target_field=target_field, transform=self.name,
                              n_total=len(series))
        # Resolve distinct values once (the privacy-preserving unit of work).
        lookup = self._resolver.resolve_distinct(series.tolist())
        # Map normalised value -> Match so each row can be assigned.
        from ..resolve import normalize
        norm_to_match = {normalize(v): m for v, m in lookup.items()}

        out = []
        for i, val in enumerate(series.tolist()):
            m = norm_to_match.get(normalize(val)) if val is not None else None
            if m is None or m.band == "unresolved":
                best = m.canonical if m else None
                guess = f"; best guess {best} @ {m.score:.2f}" if (m and best) else ""
                out.append(val)
                res.n_flagged += 1
                res.flags.append(Change(i, val, val, True, f"unresolved{guess}"))
            elif m.band == "review":
                out.append(m.canonical)
                res.n_changed += _s(m.canonical) != _s(val)
                res.n_flagged += 1
                res.flags.append(Change(i, val, m.canonical, True,
                                        f"review: matched {m.canonical} @ {m.score:.2f}"))
                if len(res.examples) < 5:
                    res.examples.append(Change(i, val, m.canonical))
            else:  # high
                out.append(m.canonical)
                if _s(m.canonical) != _s(val):
                    res.n_changed += 1
                    if len(res.examples) < 5:
                        res.examples.append(Change(i, val, m.canonical))

        res.series = pd.Series(out, index=series.index, name=target_field)
        return res

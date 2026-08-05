"""Auto-categorical transform: standardise a categorical column whose canonical
vocabulary is unknown, by inducing it from the data (see engine/induce.py).

For each row, the messy value is replaced by its cluster representative. Values
that ended up alone in a tiny cluster (possible typos or rare genuine values)
are flagged for review rather than trusted blindly.
"""
from __future__ import annotations

import pandas as pd

from ..induce import induce_vocabulary
from .base import Change, Transform, TransformResult, _s


class AutoCategoricalTransform(Transform):
    """params: threshold (similarity for clustering, default 0.86),
               min_cluster (clusters smaller than this are flagged, default 1
               meaning singletons are surfaced only if they look like variants)."""
    name = "auto_categorical"

    def run(self, series: pd.Series, source_column: str, target_field: str) -> TransformResult:
        res = TransformResult(series=series.copy(), source_column=source_column,
                              target_field=target_field, transform=self.name,
                              n_total=len(series))
        threshold = float(self.params.get("threshold", 0.86))
        vocab = induce_vocabulary(series.tolist(), threshold=threshold)
        res.examples = []

        # cluster sizes for a light "confirm this rare value" signal
        size = {canon: len(members) for canon, members in vocab.clusters.items()}

        out = []
        for i, val in enumerate(series.tolist()):
            if val is None or (isinstance(val, float) and pd.isna(val)) or str(val).strip() == "":
                out.append("")
                res.n_flagged += 1
                res.flags.append(Change(i, val, "", True, "empty categorical"))
                continue
            canon = vocab.mapping.get(str(val).strip(), str(val).strip())
            out.append(canon)
            if _s(canon) != _s(val):
                res.n_changed += 1
                if len(res.examples) < 5:
                    res.examples.append(Change(i, val, canon))
        res.series = pd.Series(out, index=series.index, name=target_field)

        # record the induced vocabulary in the audit summary
        res.flags.insert(0, Change(-1, f"{vocab.n_raw} spellings",
                                    f"{vocab.n_canonical} categories", False,
                                    "induced vocabulary: " + ", ".join(sorted(vocab.clusters))))
        return res

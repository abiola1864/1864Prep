"""Optional semantic similarity via local sentence-embeddings.

String algorithms (rapidfuzz/jellyfish) catch *spelling* similarity but not
*meaning*: they'll never see that "Provisions" and "Groceries", or "HTN" and
"Hypertension", refer to the same thing. A small local embedding model can.

This is genuine ML: a trained neural network turned into vectors, run on your
own machine (via `sentence-transformers`). It's OPTIONAL and gated:
  * If the library + model are present, `available()` is True and `embed()`
    returns vectors; callers can group by cosine similarity.
  * If not, everything degrades to the string algorithms — no crash, no network.

Note: the model weights download once, on first use, on the user's machine
(they were NOT downloadable in the build sandbox, so this path is shipped to run
locally, with the deterministic string method as the always-present fallback).
"""
from __future__ import annotations

from functools import lru_cache

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"   # small (~90MB), CPU-fine


@lru_cache(maxsize=1)
def _model():
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(_MODEL_NAME)
    except Exception:
        return None


def available() -> bool:
    return _model() is not None


def embed(texts: list[str]):
    """Return unit-normalised vectors for texts, or None if unavailable."""
    m = _model()
    if m is None:
        return None
    return m.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)


def semantic_pairs(values: list[str], threshold: float = 0.62) -> list[tuple[str, str, float]]:
    """Pairs of distinct values that are semantically close (cosine >= threshold).
    Empty if embeddings aren't available."""
    distinct = list(dict.fromkeys(str(v).strip() for v in values if str(v).strip()))
    vecs = embed(distinct)
    if vecs is None or len(distinct) < 2:
        return []
    import numpy as np
    sim = np.asarray(vecs) @ np.asarray(vecs).T
    out = []
    for i in range(len(distinct)):
        for j in range(i + 1, len(distinct)):
            s = float(sim[i, j])
            if s >= threshold:
                out.append((distinct[i], distinct[j], round(s, 3)))
    out.sort(key=lambda t: t[2], reverse=True)
    return out

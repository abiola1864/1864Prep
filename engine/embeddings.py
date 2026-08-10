"""A pluggable semantic-embedding layer with graceful fallback.

The engine calls one interface; three backends are tried in order:
  1. sentence-transformers  (best quality; downloads a model once)
  2. model2vec              (small, fast static embeddings; downloads once)
  3. lexical                (deterministic char n-gram vectors; always works,
                             offline, no download - lexical similarity only)

This means every feature built on embeddings runs everywhere: excellent where a
model is installed, still functional where none is. The active backend is
reported honestly via `get_embedder().backend` so the UI/logs never imply a
neural model when only the lexical fallback is present.

Design rule: embeddings widen RECALL (surface more candidate matches). They must
never DECIDE identity on their own - facts are settled by the reference layer
(engine.domains / engine.ng_admin) and by user confirmation. See engine notes.
"""
from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

try:
    import numpy as np
except Exception:                       # numpy is a core dep, but stay defensive
    np = None

_WORD = re.compile(r"[a-z0-9]+")
_LEX_DIM = 256


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


class _LexicalEmbedder:
    """Deterministic fallback: hash char 3-grams + word tokens into a fixed,
    L2-normalised vector. Captures spelling/token overlap (good for typos and
    rewordings) but NOT deep meaning - 'Provisions' vs 'Groceries' will be low.
    Honest by design; upgrades automatically when a real model is installed."""
    backend = "lexical"
    dim = _LEX_DIM

    def _vec(self, text: str):
        v = [0.0] * _LEX_DIM
        t = _norm_text(text)
        if not t:
            return v
        toks = _WORD.findall(t)
        grams = [t[i:i + 3] for i in range(max(0, len(t) - 2))] + toks
        for g in grams:
            h = int(hashlib.md5(g.encode()).hexdigest(), 16)
            v[h % _LEX_DIM] += 1.0
        n = math.sqrt(sum(x * x for x in v))
        return [x / n for x in v] if n else v

    def encode(self, texts):
        rows = [self._vec(t) for t in texts]
        return np.array(rows, dtype="float32") if np is not None else rows


class _STEmbedder:
    backend = "sentence-transformers"

    def __init__(self, model):
        self._m = model

    def encode(self, texts):
        return self._m.encode(list(texts), normalize_embeddings=True,
                              show_progress_bar=False)


class _M2VEmbedder:
    backend = "model2vec"

    def __init__(self, model):
        self._m = model

    def encode(self, texts):
        import numpy as _np
        v = self._m.encode(list(texts))
        n = _np.linalg.norm(v, axis=1, keepdims=True)
        n[n == 0] = 1.0
        return (v / n).astype("float32")


@lru_cache(maxsize=1)
def get_embedder(prefer: str = "auto"):
    """Return the best available embedder (cached). Order: sentence-transformers
    -> model2vec -> lexical. Never raises; always returns something usable."""
    if prefer in ("auto", "sentence-transformers"):
        try:
            from sentence_transformers import SentenceTransformer
            return _STEmbedder(SentenceTransformer("all-MiniLM-L6-v2"))
        except Exception:
            pass
    if prefer in ("auto", "model2vec"):
        try:
            from model2vec import StaticModel
            return _M2VEmbedder(StaticModel.from_pretrained("minishlab/potion-base-8M"))
        except Exception:
            pass
    return _LexicalEmbedder()


def is_semantic() -> bool:
    """True only when a real neural backend is active (not the lexical fallback)."""
    return get_embedder().backend in ("sentence-transformers", "model2vec")


def cosine(a, b) -> float:
    if np is not None:
        a = np.asarray(a, dtype="float32"); b = np.asarray(b, dtype="float32")
        na = float(np.linalg.norm(a)); nb = float(np.linalg.norm(b))
        return float(a @ b / (na * nb)) if na and nb else 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def embed(texts):
    return get_embedder().encode(list(texts))


def semantic_pairs(values, threshold: float = 0.62):
    """Yield (a, b, score) for value pairs whose MEANING is close. Only meaningful
    with a neural backend; with the lexical fallback this reduces to string overlap
    (already handled elsewhere), so callers should gate on `is_semantic()`."""
    vals = [str(v) for v in values if str(v).strip()]
    if len(vals) < 2:
        return []
    M = embed(vals)
    out = []
    n = len(vals)
    for i in range(n):
        for j in range(i + 1, n):
            s = cosine(M[i], M[j])
            if s >= threshold:
                out.append((vals[i], vals[j], round(float(s), 3)))
    return out

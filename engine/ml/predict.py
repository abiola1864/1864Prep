"""Load the trained type classifier and predict a column's type + confidence.

This is an OPTIONAL assist. The rule-based profiler stays in charge; the
classifier is consulted to break ties or rescue columns the rules mis-read
(e.g. mostly-numbers polluted with worded junk). If the model file is absent,
everything degrades to the rules — no hard dependency.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .features import column_features

_MODEL_PATH = Path(__file__).resolve().parent / "typeclf.joblib"


@lru_cache(maxsize=1)
def _load():
    try:
        import joblib
        if _MODEL_PATH.exists():
            return joblib.load(_MODEL_PATH)
    except Exception:
        pass
    return None


def predict_type(values, model=None) -> tuple[str | None, float]:
    """Return (type, confidence in 0..1) or (None, 0.0) if no model available."""
    t, c, _ = predict_detail(values, model)
    return t, c


def predict_detail(values, model=None) -> tuple[str | None, float, float]:
    """Return (type, top_confidence, margin_over_second). Margin is a better
    'is this a clear winner?' signal than absolute confidence in a many-class
    problem."""
    clf = model or _load()
    if clf is None:
        return None, 0.0, 0.0
    proba = clf.predict_proba([column_features(values)])[0]
    order = sorted(proba, reverse=True)
    i = int(proba.argmax())
    margin = float(order[0] - (order[1] if len(order) > 1 else 0.0))
    return clf.classes_[i], float(proba[i]), margin


def available() -> bool:
    return _load() is not None

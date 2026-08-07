"""General NLP layer (optional, one downloaded model).

Uses a spaCy model for what a general model is genuinely good at:
  * NER column typing  -> what KIND of entity a column holds (person, org,
    place, money, date, product...), for ANY data, not per-domain lists.

Honest limits (measured, not assumed):
  * NER types entities; it does NOT resolve identity ("Niger" and "Nigeria" are
    both GPE). Identity comes from the domains module (country_converter /
    pycountry) or a knowledge base.
  * spaCy's static word vectors are too weak for reliable meaning-matching
    ("Provisions" vs "Groceries"); good semantic similarity needs
    sentence-transformers (see engine/ml/embed.py), a separate optional model.

Install the model once (from GitHub, no HuggingFace needed):
    pip install "https://github.com/explosion/spacy-models/releases/download/en_core_web_md-3.8.0/en_core_web_md-3.8.0-py3-none-any.whl"
If absent, every function here degrades to None and the engine is unaffected.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache

# spaCy label -> our column type (only the ones we can act on)
_LABEL_TO_TYPE = {
    "PERSON": "name", "GPE": "geo", "LOC": "geo", "FAC": "geo",
    "ORG": "organization", "MONEY": "numeric", "PERCENT": "numeric",
    "QUANTITY": "numeric", "DATE": "date", "TIME": "datetime",
}


@lru_cache(maxsize=1)
def _nlp():
    try:
        import spacy
        for model in ("en_core_web_md", "en_core_web_lg", "en_core_web_sm"):
            try:
                return spacy.load(model, disable=["parser", "lemmatizer"])
            except Exception:
                continue
    except Exception:
        pass
    return None


def available() -> bool:
    return _nlp() is not None


def column_entity_type(values, sample: int = 60) -> tuple[str | None, float]:
    """(our_type, confidence) for the dominant NER label in a column, or
    (None, 0.0) if unavailable or nothing dominates."""
    nlp = _nlp()
    if nlp is None:
        return None, 0.0
    vals = [str(v).strip() for v in values if str(v).strip()][:sample]
    if not vals:
        return None, 0.0
    labels = []
    for doc in nlp.pipe(vals):
        ents = list(doc.ents)
        if ents and len(ents[0].text) >= max(3, int(0.6 * len(doc.text))):
            labels.append(ents[0].label_)
    if not labels:
        return None, 0.0
    label, n = Counter(labels).most_common(1)[0]
    return _LABEL_TO_TYPE.get(label), n / len(vals)

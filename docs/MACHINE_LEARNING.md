# Machine learning in the engine — what's real, what's optional

The engine is **deterministic-first** on purpose: rules and classical string
algorithms (rapidfuzz, jellyfish) plus proven libraries (phonenumbers,
dateparser, price-parser). That's what makes every change explainable and
offline. ML is added only where it genuinely helps, and never silently changes
data.

## 1. Trained column-type classifier (active)

`engine/ml/` contains a small **scikit-learn RandomForest** trained on synthetic
labelled columns (`train_typeclf.py`; never real data). It reads a column's
*shape* features (fraction numeric/date/boolean, distinct ratio, token/length,
id/email/phone patterns) and predicts the type with a confidence.

It's an **assist**, not a replacement: the rules stay authoritative, and the
model is only consulted to rescue columns the rules mis-read — e.g. a
mostly-numeric age column polluted with "Do not know"/"N/A" that the rules would
otherwise call "categories". Guards prevent bad flips (long ID numbers stay
identifiers; identifier↔phone is left alone as too ambiguous). If scikit-learn
or the model file is missing, the engine degrades to rules with no error.

Retrain any time: `python -m engine.ml.train_typeclf` → `engine/ml/typeclf.joblib`.

## 2. Semantic similarity via local embeddings (optional)

`engine/ml/embed.py` can use a small local **sentence-embedding** model
(`sentence-transformers`, ~90MB, CPU-fine) to catch *meaning-based* matches the
string algorithms miss — "Provisions" ≈ "Groceries", "HTN" ≈ "Hypertension".
When present, it strengthens the worklist's similar-value grouping (still never
merging across different numbers, still suggest-only). When absent, grouping
falls back to the string algorithms. Install with the `semantic` extra; the
model downloads once, locally, on first use.

## What is NOT here

There is **no transfer learning and no custom-trained large model**. The
"improve the tool" path collects opt-in *correction pairs* into a shared
dictionary — curated data that could feed a trained model later, but is not one
now. We say so plainly rather than overclaiming.

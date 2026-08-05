# Learning from your corrections, and the per-field review

Two ideas drive this layer: the tool should already know what it has been taught,
and for every field it should predict the ideal ("perfect world") and then walk
you through confirming or adjusting it.

## It learns from the mistakes you share — and keeps learning

Every correction the team has shared is compiled into a **correction memory**
(`knowledge/seed_corrections.json`, built from the data/scripts you sent). The
resolver consults it *first*: a known correction is a certainty, not a guess.

- `Port Harcourt → RIVERS`, `Ibadan → OYO`, `Onitsha → ANAMBRA` resolve as
  **learned** (method `learned`, score 1.0) — string similarity alone could
  never do this, because a city name looks nothing like its state. The knowledge
  came from you.
- A spelling the memory has never seen (`Lasgos`) is still caught by fuzzy +
  phonetic matching. Memory and similarity cover different gaps.

And it grows. When you confirm or fix a suggestion in review, `store.learn(...)`
appends it to `knowledge/user_corrections.json`; from then on that value is
certain, in this and every future session. Teaching `Uyo → AKWA IBOM` once means
the tool never asks again.

### Conflicts are surfaced, never guessed

Where the shared data itself disagreed — `Abuja(Jos)` was tagged both `FCT` and
`PLATEAU` — the tool keeps both candidates and **asks you** rather than silently
picking one. Resolving the conflict once records your decision and clears it.

## Per-field "perfect world" prediction (`engine/predict.py`)

For every column, before any cleaning, the tool predicts a **field spec**:

- **Predicted field name** — `Ph No → Phone (MSISDN)`, `Sex → Gender`,
  `State of Origin → State`, `D.O.B → Date of Birth`. A recognised header is a
  strong prior: it decides the field's *type* when it disagrees with a
  low-confidence statistical guess (so `Sex` with values `M/F/1/2` is Gender, not
  a mystery categorical; `Email` stays email even when one value is malformed).
- **Semantic type + target standard** — the ideal form the values should take
  (`+234XXXXXXXXXX`, `YYYY-MM-DD`, one of 37 states UPPERCASE, an induced category
  set, …).
- **The questions to walk you through** — specific, per field. Examples the tool
  actually generates on an 18-field file:
  - *Phone*: "Normalise all numbers to +234 (E.164)? Non-Nigerian numbers flagged."
  - *11-digit ID*: "Is this a NIN, a BVN, or another 11-digit identifier? (format
    alone can't tell them apart)"
  - *Date*: "Day-first (DD/MM) or month-first (MM/DD)? I'll standardise to
    YYYY-MM-DD."
  - *State*: "7 distinct values: 6 resolved from what you've taught me, 0 to
    confirm; 1 I can't place — Abuja(Jos). Tell me and I'll remember it."
  - *Categorical (Diagnosis)*: "10 spellings group into 5 categories:
    [Diabetes, HTN, Hypertension, Malaria, Typhoid]. Confirm or rename these?"

This scales to files with many fields — each field is one compact review item,
which is exactly what the mockup's step-4 screen renders.

## The loop, end to end

1. **Predict** the perfect form for every field (name, type, standard, values).
2. **Apply what's known** — learned corrections and confident matches resolve
   automatically; only the uncertain and the conflicts reach you.
3. **You adjust** — confirm, rename a category, pick a state for an unplaced
   value, set the date order, say NIN vs BVN.
4. **It learns** — every answer is written back to the correction memory and
   improves the next file, the next agency, the next sector.

## Honest limits (unchanged, and where the model rung helps)

- Memory + fuzzy + phonetic cannot infer a place it has never been taught and
  that doesn't resemble a canonical name. That is the gazetteer + local-model
  rung: a model with world knowledge proposes `Nsukka → Enugu` the first time,
  you confirm, and it becomes memory.
- Two 11-digit IDs (NIN vs BVN) are indistinguishable by format; the tool asks.
- Category clustering is by spelling/sound, so `HTN` and `Hypertension` don't
  merge automatically — a semantic (embedding/model) step merges those, still on
  distinct values only.
- Every prediction carries a confidence; low-confidence fields and all
  unresolved values go to you, never through silently.

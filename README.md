# 1864 Prep

**Local, consent-first data standardisation for the Open Network on Digital ID.**

An agency points the tool at its records — however messy, whatever the columns —
and it standardises them **on the agency's own machine**, proposes every change,
and lets a person approve them before anything is saved. Nothing is uploaded.
The agency then chooses, column by column, what (if anything) the network may ask.

Two guarantees run through everything:

1. **Data never leaves the machine.** The desktop app cleans locally; the hosted
   demo is for synthetic data only.
2. **Nothing meaning-changing happens without consent.** Every change is a
   proposal shown in review; the person accepts, edits, or keeps the original.

---

## What's in this repository

- **`engine/`** — the cleaning engine (deterministic core + optional ML). Reads
  messy files, works out what each column is, proposes fixes, and records every
  change. UI-independent and fully tested.
- **`app/`** — a small web service (`server.py`) around the engine and a desktop
  shell (`desktop.py`). The same code powers the hosted demo and the offline app.
- **`prototype/ui/`** — the clickable wizard (sign in → sector → columns → upload
  → match → review → **needs attention** → export) plus a Settings screen.
- **`regions/`** — swappable country packs. The engine is generic; Nigeria is one
  pack. Add a country in a few lines.
- **`reference/`, `knowledge/`, `plans/`, `samples/`, `tests/`, `docs/`** — lookup
  data, learned corrections, example plans, synthetic sample data, tests, and
  design notes.

---

## What the engine can do

### Reads messy files (any of these)
CSV / TSV / TXT (sniffs encoding, delimiter, and the real header row past banner
rows), Excel (multi-sheet, picks the fullest), JSON (flattens nested keys), and
**PDF** (extracts tables, merges across pages). See `engine/ingest.py`.

### Works out each column's type
Rule-based detection, **assisted by a trained machine-learning classifier**
(`engine/ml/`) that rescues columns the rules mis-read — e.g. a mostly-numeric
age column polluted with "Do not know" is still recognised as numeric. Types
include: numeric, date, **datetime/timestamp**, phone, email, identifier, name,
geographic, categorical, boolean, gender, **0/1 indicator (leave-alone)**,
free-text, and empty.

### Cleans, using established libraries (not bespoke rules)
- **Phones** → any country via `phonenumbers` (region is a parameter)
- **Dates & timestamps** → many formats + Excel serials via `dateparser`
- **Numbers & currency** → `price-parser` (₦/$/€, thousands separators,
  comma-vs-dot decimals, parentheses-negatives, %)
- **Unit-aware numbers** → "3200g" → 3200, optional convert to kg/ha/… via `pint`
- **Text / encoding** → `ftfy` (mojibake), zero-width/whitespace/quote normalising
- **Email** → validated & normalised via `email-validator`
- **Missing values** → the many spellings of "missing" treated consistently
- **Sentinel/refusal codes** (998/999/-99/"don't know") → missing + flagged
- **Range/outlier checks** (e.g. age 0–120) → flag out-of-range

### Standardises categories safely
Merges only same-meaning spellings (case, spacing, "&"/"and", word order);
**never** merges across different words or different numbers. Genuine typos and
look-alikes are offered as *suggestions*, never applied automatically.

### Finds duplicates & similar entries
Duplicate/near-duplicate rows, and **graded similarity clusters** (very likely /
possibly the same) that you confirm with a tap — tick the matches, edit one name,
combine. Optional local **semantic embeddings** (`sentence-transformers`) catch
meaning-based matches ("Provisions" ≈ "Groceries") when installed.

### Reshapes (explicit actions, never silent)
Split a column (by delimiter, name → first/surname, "text + number"), merge
columns, and extract date parts (year/month).

### "Needs your attention" worklist
Everything that needs judgement in one place: columns you kept as original,
flagged values, duplicate rows, similar-value groups, and repeated columns — each
with simple actions. Nothing changes automatically.

### Learns
A correction store remembers confirmed fixes and reuses them. Optional, opt-in
contribution of *correction pairs only* (never records) can improve a shared
dictionary in future updates. There is **no transfer learning / custom large
model** — that's a future path, stated honestly, not a current feature.

---

## Quickstart

```bash
pip install -e .            # Python 3.11+
python cli.py transforms    # list the cleaning transforms
python -m pytest -q         # run the tests (or: for t in tests/*.py; do python "$t"; done)
```

Run the app locally (wizard + live engine):

```bash
pip install -e ".[web]"
uvicorn app.server:app --reload      # http://127.0.0.1:8000
```

See `docs/DEPLOY.md` for hosting the demo (Render) and packaging the desktop app
(pywebview + PyInstaller, Mac + Windows via GitHub Actions).

---

## Region packs (generic by design)

```python
import regions
regions.set_active_region("ng")        # Nigeria pack (phone NG, day-first dates, states/LGAs)
# add another country in a few lines — see regions/README.md
```

Set `PREP_REGION=ng` for the server; the engine itself defaults to generic.

---

## Machine learning — what's real

- **Active:** a trained scikit-learn classifier assists column-type detection
  (`engine/ml/`, retrain with `python -m engine.ml.train_typeclf`).
- **Optional:** local sentence-embeddings for semantic similarity.
- **Not present:** transfer learning or a custom-trained large model.

See `docs/MACHINE_LEARNING.md`.

---

## Documentation

`docs/ARCHITECTURE.md` · `docs/CLEANING_APPROACH.md` · `docs/GENERALITY.md` ·
`docs/INGESTION_AND_TEXT.md` · `docs/LEARNING_AND_REVIEW.md` ·
`docs/MACHINE_LEARNING.md` · `docs/DEPLOY.md` · `regions/README.md`

## Licence

Apache-2.0 (see `LICENSE`).

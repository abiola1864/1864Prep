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

## Table of contents
- [How it works (the flow)](#how-it-works-the-flow)
- [Repository layout](#repository-layout)
- [Reading files](#reading-files)
- [Column types the engine recognises](#column-types-the-engine-recognises)
- [Cleaning transforms (full list)](#cleaning-transforms-full-list)
- [Reshaping operations](#reshaping-operations)
- [Duplicates & similarity](#duplicates--similarity)
- [The "Needs your attention" worklist](#the-needs-your-attention-worklist)
- [Machine learning](#machine-learning)
- [Region packs](#region-packs)
- [Learning & contribution](#learning--contribution)
- [Quickstart & running the app](#quickstart--running-the-app)
- [Tests](#tests)
- [Honest limitations](#honest-limitations)

---

## How it works (the flow)

```
Sign in → Sector → Choose columns → Upload a file
   → Match column names → Review (column by column)
   → Needs your attention (worklist) → Export (+ optional Open-Network sharing)
```

1. **Read** the file (`engine/ingest.py`): any format below, sniffing encoding,
   delimiter and the real header row.
2. **Profile** each column (`engine/profile.py`): rules + column-name hints +
   a trained ML classifier decide the type.
3. **Plan & clean** (`engine/pipeline.py`): each column is mapped to a transform;
   nothing is applied blindly — a full record of before/after is produced.
4. **Review** (`engine/review.py`): every distinct change shown, grouped by
   result, searchable; you accept or keep the original per column.
5. **Worklist** (`engine/dedupe.py` + review): rejected columns, flagged values,
   duplicates, similar-value groups, repeated columns — decided by you.
6. **Export**: apply approved changes; optionally expose per-column verified
   answers to the Open Network (raw records never move).

---

## Repository layout

| Path | What it is |
|---|---|
| `engine/` | The cleaning engine. Deterministic core + optional ML. UI-independent. |
| `engine/ingest.py` | Robust multi-format reader (CSV/TSV/TXT, Excel, JSON, PDF). |
| `engine/profile.py` | Column-type detection: rules + header hints + ML assist. |
| `engine/transforms/` | One cleaning rule per file (see the transform list below). |
| `engine/resolve.py` | Fuzzy + phonetic matching to a canonical list. |
| `engine/induce.py` | Category standardisation (same-meaning merge only). |
| `engine/dedupe.py` | Duplicate rows, graded similarity clusters, duplicate columns. |
| `engine/reshape.py` | Split / merge columns, date parts, geopoint split. |
| `engine/textclean.py` | Free-text normalisation, language detect, extraction. |
| `engine/knowledge.py`, `engine/predict.py` | Learned-correction store + reuse. |
| `engine/ml/` | Trained type classifier + optional local embeddings. |
| `regions/` | Swappable country packs (Nigeria = one pack; `GENERIC` default). |
| `app/` | Web service (`server.py`) + desktop shell (`desktop.py`). |
| `prototype/ui/` | The wizard + Settings screen (HTML). |
| `reference/`, `knowledge/`, `plans/`, `samples/`, `tests/`, `docs/` | Support. |

---

## Reading files

`engine/ingest.py` → `read_any(path)` returns a clean table + a report of what
it detected:

| Format | Handling |
|---|---|
| CSV / TSV / TXT | sniff encoding; sniff delimiter by consistency across lines; skip banner rows to find the real header; pad/trim ragged rows |
| Excel (.xlsx/.xls/.xlsm) | read all sheets, pick the fullest, detect header row |
| JSON | flatten nested keys to dotted columns (`person.name`) |
| PDF | extract ruled tables, merge across pages; text-line fallback |

---

## Column types the engine recognises

Detected from values, the **column name**, and a trained classifier:

`numeric` · `latitude` · `longitude` · `geopoint` · `date` · `datetime` ·
`phone` · `email` · `identifier` · `name` · `geo` (place) · `categorical` ·
`boolean` · `gender` · `indicator` (0/1 dummy — left alone) · `free_text` ·
`empty`.

**Header-aware:** a column called `lat`/`latitude` or `long`/`lng` is recognised
as a coordinate even though its values are just decimals — the exact case
values-only detection misses. Hints also help `phone`, `email`, `date`,
`amount/fee`, `sex/gender`.

---

## Cleaning transforms (full list)

Every transform proposes changes and records before/after; flagged values are set
aside for review, never silently altered.

| Transform | Does | Example |
|---|---|---|
| `text_clean` | repair encoding (mojibake), strip zero-width, normalise quotes/whitespace, NA-tokens → blank | `Ã©` → `é`; `  N/A ` → `` |
| `text_normalise` | basic trim + whitespace collapse | `  a  b ` → `a b` |
| `name` | trim, collapse spaces, title-case | `chidi   OKAFOR` → `Chidi Okafor` |
| `upper` | uppercase | `abia` → `ABIA` |
| `gender` | standardise sex values | `M`, `male`, `boy` → `Male` |
| `boolean` | standardise yes/no | `Y`, `true`, `1` → `Yes` |
| `numeric` | currency/thousands/decimals, **keeps negatives**, parens-negatives, % (via price-parser) | `N1,200.50` → `1200.5`; `(200)` → `-200`; `-99` → `-99` |
| `unit_numeric` | number carrying a unit → number; optional convert (via pint) | `3200g` → `3200`; to kg → `3.2` |
| `sentinel_na` | refusal/DK codes → missing + flag | `999`, `-99`, `don't know` → `` |
| `range_check` | flag values outside min/max | age `200` → flagged |
| `date_iso` | many date formats + Excel serials → `YYYY-MM-DD` (via dateparser) | `3/9/1990` → `1990-09-03`; `44197` → date |
| `datetime_iso` | timestamps → `YYYY-MM-DD HH:MM:SS` | `2019-05-03 12:41:15` |
| `latitude` | → decimal degrees, range −90..90 (via lat-lon-parser) | `6°27'N` → `6.45`; `200` flagged |
| `longitude` | → decimal degrees, range −180..180 | `30.123W` → `-30.123` |
| `phone` / `phone_ng` | → E.164 for the active region (via phonenumbers) | `08031234567` → `+2348031234567` |
| `email` | validate + normalise (via email-validator) | `ADA@X.IO` → `ada@x.io` |
| `nin` / `fixed_id` | fixed-length ID checks | flags wrong-length IDs |
| `state_ng` / `lga_ng` | match to official states / LGAs | `Kastina` → `Katsina` |
| `resolve` | fuzzy + phonetic match to a canonical list | `Lgos` → `Lagos` |
| `auto_categorical` | induce a vocabulary, merge same-meaning spellings only | `drinks, wine & spirits` = `Drinks, Wine and Spirits` |

`cli.py transforms` prints the live list.

---

## Reshaping operations

Change table shape, so offered as explicit actions (`engine/reshape.py`):

- `split_by_delimiter` — `Lagos, Nigeria` → two columns
- `split_name` — `ADEYEMI, Tunde` → first / surname
- `split_number_text` — `Musa 34` → text + number
- `split_geopoint` — `6.45, 3.39` → latitude / longitude
- `merge_columns` — join several columns into one
- `date_part` — extract year / month from a date column

---

## Duplicates & similarity

- **Duplicate / near-duplicate rows** (`near_duplicate_rows`).
- **Graded similarity clusters** (`cluster_similar`): groups scored *very likely*
  / *possibly* the same; you confirm with a tap (tick matches, edit one name,
  combine). Never merges across different numbers.
- **Duplicate columns** (`duplicate_columns`): repeated headers grouped.
- **Optional semantic** grouping via local embeddings (see ML).

---

## The "Needs your attention" worklist

One place for everything needing judgement, none of it applied automatically:
columns you kept as original · flagged values (with reasons) · duplicate rows ·
similar-value groups (tap-to-combine) · repeated columns. Actions: *try a
different clean*, *set all to…*, *combine*, *remove duplicates*, *keep as-is*.

---

## Machine learning

- **Active — type classifier** (`engine/ml/`): scikit-learn RandomForest trained
  on synthetic labelled columns; assists the rules, e.g. rescues a mostly-numeric
  age column polluted with "Do not know". Retrain: `python -m engine.ml.train_typeclf`.
- **Optional — semantic embeddings** (`engine/ml/embed.py`): local
  sentence-transformers model for meaning-based matches (`Provisions` ≈
  `Groceries`); falls back to string similarity when not installed.
- **Not present:** transfer learning / a custom-trained large model. See
  `docs/MACHINE_LEARNING.md`.

---

## Region packs

The engine is generic; a country is a swappable pack (`regions/`).

```python
import regions
regions.set_active_region("ng")   # Nigeria: phone NG, day-first dates, states/LGAs
```

Add a country in a few lines (see `regions/README.md`). Set `PREP_REGION=ng` for
the server; the engine itself defaults to `generic`.

---

## Learning & contribution

`engine/knowledge.py` remembers confirmed corrections and reuses them. An opt-in
setting can contribute *correction pairs only* (never records) to improve a
shared dictionary in future updates. Off by default.

---

## Quickstart & running the app

```bash
pip install -e .            # Python 3.11+
python cli.py transforms    # list transforms
python -m pytest -q         # run tests

pip install -e ".[web]"
uvicorn app.server:app --reload      # http://127.0.0.1:8000
```

Hosting the demo (Render) and packaging the desktop app (pywebview + PyInstaller,
Mac + Windows via GitHub Actions): see `docs/DEPLOY.md`.

Optional extras: `.[semantic]` (embeddings), `.[desktop]` (packaging).

---

## Tests

Run all: `for t in tests/*.py; do python "$t"; done` (or `pytest -q`). Suites:
transforms, resolver, profile/induce, learning, ingest/textclean, dedupe,
regions, ML, validate/reshape, coordinates.

---

## Honest limitations

- The **hosted demo sends data to a server** — synthetic data only; the desktop
  build is the private one.
- **Semantic embeddings** need the model downloaded locally (not bundled).
- **No transfer learning / custom model** yet — that's a future path fed by
  opt-in correction pairs.
- Meaning-based resolution (`Port Harcourt` → `Rivers` without a gazetteer entry;
  `HTN` ≈ `Hypertension`) needs the optional AI layer, not the deterministic core.
- Worklist / split-merge decisions are **recorded**; applying them to the exported
  file is the current work-in-progress.

## Licence
Apache-2.0 (see `LICENSE`).

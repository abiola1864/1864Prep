# 1864 Prep

Local, consent-first data standardisation for the **Open Network on Digital ID**.

An agency points the tool at its records — however messy, whatever the columns —
and it standardises them **on the agency's own machine**, proposes the changes,
and lets a person approve them before anything is saved. Nothing is uploaded.
The agency then chooses, column by column, what (if anything) the network may ask.

This repository holds two things:

- **`engine/`** — the real cleaning engine (Python). Deterministic, testable,
  UI-agnostic. This is the durable core.
- **`prototype/ui/`** — clickable HTML prototypes of the wizard and the review
  screen. These are a **specification of the experience**, not the shipping UI
  (see *Roadmap*).

## What the engine does (and what is / isn't AI)

Most of the work is **deterministic algorithms, no AI**: type detection,
format cleaning (IDs, phones, dates, emails, numbers, yes/no, names), fuzzy +
phonetic matching (`Kastina → Katsina`), vocabulary induction, a learning
knowledge base of confirmed corrections, and outlier detection. All local, no
account, no internet.

**AI is an optional layer** for the hard, meaning-based cases only — world-
knowledge place resolution (`Port Harcourt → Rivers`, unless supplied as a
gazetteer), synonym matching (`HTN ≈ Hypertension`), and free-text. It is off by
default and, when on, connects to a local/on-prem or approved cloud model. See
`docs/CLEANING_APPROACH.md`.

## Quickstart (engine)

```bash
pip install -e .            # Python 3.11+
python cli.py transforms    # list the cleaning transforms
python samples/make_sample.py
python cli.py clean samples/social_register_sample_raw.xlsx --plan plans/social_register.json --out out
python -m pytest -q         # run the tests
```

## Prototype UI

Open `prototype/ui/1864_prep_app.html` in a browser — the full wizard:
sector → choose columns (by meaning) → upload → match column names → clean
(built-in, or AI-assisted via a toggle) → sequential review (✓ looks right /
✗ keep original) → export with per-column network permissions.

## What's in each folder

- **`engine/`** — the cleaning engine itself (the code that does the work). Inside it:
  `profile.py` works out what each column is; `resolve.py` matches messy values to a
  correct list using spelling + sound; `induce.py` discovers a category set from the
  data; `knowledge.py` remembers corrections it has been given; `review.py` builds the
  before/after summaries; `pipeline.py` runs a cleaning plan end to end; and
  `transforms/` holds one small, tested rule per file (IDs, phones, dates, emails,
  numbers, names, states, etc.).
- **`plans/`** — example cleaning plans. A plan is a short list saying "clean this
  column with this rule" — what the tool proposes after reading a file.
- **`reference/`** — the lookup data the engine matches against: the official states,
  a places→state gazetteer, example LGA lists. Swap these to adapt to another country.
- **`knowledge/`** — the corrections the tool has learned (starts from
  `seed_corrections.json` and grows as people confirm fixes).
- **`samples/`** — generators that create synthetic, deliberately messy data.
  **`samples/data/`** holds ready-made example files, one per sector, so you can see
  the kind of input the tool cleans. None of it is real data.
- **`tests/`** — automated checks that the cleaning behaves correctly.
- **`docs/`** — design notes (architecture, cleaning approach, handling unseen data,
  learning + review).
- **`prototype/ui/`** — clickable HTML mockups of the wizard and review screen. These
  show the intended experience; they are **not** the final app (see Roadmap).
- **Top level** — `cli.py` (run the engine from a terminal), `pyproject.toml`
  (dependencies), `README.md`, `LICENSE`, `CONTRIBUTING.md`.

### Sample data

`samples/data/` has one synthetic file per sector so you can open example inputs:

```
samples/data/health_sample.csv
samples/data/agriculture_sample.csv
samples/data/education_sample.csv
samples/data/social_protection_sample.csv
samples/data/finance_sample.csv
```

Regenerate any time with `python samples/make_sector_samples.py`. Everything in
`samples/` is synthetic — no real or private data is in this repository.

## Roadmap — toward a downloadable desktop app

The end goal is an **installable desktop application** that runs fully offline,
not a website. The plan:

1. Keep `engine/` as the stable, UI-independent core.
2. Wrap it in a desktop shell. Leading option: **Tauri** (small, secure
   installer; web UI + the Python engine as a local sidecar). Alternatives:
   Electron (heavier) or a pure-Python packager (Briefcase / PyInstaller) if we
   drop web tech entirely.
3. Rebuild the prototype's screens as the real front end inside that shell. The
   current HTML is the reference for behaviour; the shipping UI may not be plain
   HTML.
4. Ship reference data + the knowledge base inside the app so the local (no-AI)
   path is strong out of the box.

## Licence

Apache-2.0 (see `LICENSE`).

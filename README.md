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
python cli.py clean samples/socu_sample_raw.xlsx --plan plans/social_register.json --out out
python -m pytest -q         # run the tests
```

## Prototype UI

Open `prototype/ui/1864_prep_app.html` in a browser — the full wizard:
sector → choose columns (by meaning) → upload → match column names → clean
(built-in, or AI-assisted via a toggle) → sequential review (✓ looks right /
✗ keep original) → export with per-column network permissions.

## Layout

```
engine/        the cleaning engine (transforms, profiler, resolver, inducer,
               knowledge base, outlier/review, pipeline)
plans/         example cleaning plans (what the mapping layer emits)
reference/     canonical lists & gazetteer (swap to adapt to another country)
knowledge/     seed corrections the engine learns from
samples/       synthetic-data + review-report generators
tests/         transform, resolver, induction, alignment, learning tests
docs/          architecture and design notes
prototype/ui/  HTML prototypes of the wizard + review (UX spec, disposable)
```

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

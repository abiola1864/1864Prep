# 1864 Prep

**A local, consent-first tool that standardises messy government and survey data — so verified answers can join an open network without the raw data ever leaving your machine.**

Built by the 1864 Research & Innovation Institute for real field data: household surveys, farmer registries, social-protection rolls, fragile-states indices. It reads whatever you throw at it (CSV, Excel, JSON, PDF tables), works out what each column *means*, proposes clean-ups you approve one decision at a time, and produces a tidy file plus a full change log.

Two promises it keeps:

1. **Your data never leaves the computer.** The engine runs locally. The hosted demo uses synthetic data only; the desktop build keeps everything on-device.
2. **Nothing that changes meaning happens without your consent.** Every change is a proposal you accept or reject. The value is never silently rewritten.

*Non-technical reader? The first half of this page — What it does, Where it goes further, What it can't do yet — is written for you, no jargon. The technical overview comes after the divider.*

---

## What it does

- **Reads any file, figures out the schema itself.** No template, no mapping. It infers each column's type from the values — names, dates, phones, emails, IDs, coordinates, money, categories, booleans, free text — and works on files it has never seen.
- **Cleans the boring things safely.** Trims spacing, repairs broken characters, standardises case, fixes phone/email/date formatting, strips currency symbols and thousands separators — while telling you honestly that these *standardise how values look and do not change their meaning*.
- **Catches the dangerous things.** Sentinel/refusal codes (`999`, `-1`, `N/A`), impossible dates (`2024-13-99`), out-of-range values, ages of `121`, duplicate rows and columns — flagged for you, not silently "fixed."
- **Resolves real-world entities correctly.** Countries, world administrative regions (states/provinces/counties/LGAs), and currencies are matched to canonical identities using reference packages, so different-but-similar entities are never merged.
- **Reviews with you, not at you.** One sequential card per decision. Formatting-only tidies are batched into a single "accept all" screen. Merges, type changes, and flagged values get their own cards. You always see what will change before it does.
- **Exports clean data + an audit trail.** CSV, Excel, or Word, plus a change log of every accepted decision.
- **Ships a Data Toolkit** for one-off jobs: find duplicates, find outliers, match two files, validate, summarise, compare, combine, anonymise, quick-clean, and estimate gender from a name.

## Where it goes further than most tools

Most cleaners handle the obvious. These are the quieter problems that usually get missed, silently corrupt data, or cost hours of manual work — and 1864 Prep handles them locally, tested against real dirty files.

- **It reads the whole column before deciding, not one value at a time.** Many formats are impossible to read from a single cell but obvious across the column. `12.05.2021` alone could be May or December; the tool looks at the column, sees where a value passes 12, and locks the layout for every row — so one typo can't flip it. The same idea decides whether a dot means a decimal or a thousands separator, so a rate like `42.959` is never turned into `42959`.
- **It tells the difference between a value and a code.** `007`, `01234`, an account number — these only look like numbers. Treating them as numbers drops the leading zeros and destroys the code. The tool keeps them intact, and never confuses a code column with a phone or a measurement.
- **It knows which changes are safe and which change meaning.** Trimming spaces or fixing capitalisation is standardising *how a value looks*; merging two entries is changing *what it means*. The tool separates the two, breezes through the harmless ones in a single step, and only asks you about the ones that matter.
- **It refuses to invent data.** Impossible dates, out-of-range ages, refusal codes like `999` or `-1` are flagged for you, not quietly "corrected." A lone odd value is treated as a possible typo, not an excuse to reinterpret a whole column. And two values that merely look similar are only merged when they genuinely mean the same thing — different numbers, different entries, and near-but-distinct labels are kept apart.
- **It handles the mess you can't see.** Invisible characters, non-breaking spaces, byte-order marks, and garbled encoding (the `Ã©` that should be `é`) are the silent reason spreadsheets fail to join or match. The tool cleans them everywhere, automatically.
- **It finds the real table inside a messy file.** Files that open with a title, a source line, logos, or blank rows before the data begins are read correctly — the true header is found, and you're shown exactly what sat above it, never dropped without your knowledge.
- **It recognises real-world things, not just text.** People, places, organisations, money, dates, regions, currencies — the tool identifies what a column actually contains and can standardise entries to their proper form, using established reference data and optional name/entity models. It works the same on a health roll, an agriculture registry, or a global index.
- **It checks values against the known-correct set, and flags what doesn't belong.** For a column whose universe is known — administrative regions, currencies, standard categories — the tool doesn't just tidy formatting; it validates each value against the full official list. A near-miss is offered as a one-tap correction (a mistyped place name is matched to the right one). A value entered at the wrong level (a state where a local area was expected) is flagged as a level mismatch. And a value that isn't in the list at all (a city or community entered where an official area should be) is flagged for you to check. You confirm each one; nothing is changed silently.
- **It's honest about time and uncertainty.** Progress reflects the real work happening column by column and never claims "almost done" when it isn't. When something is genuinely ambiguous, it asks instead of guessing.

## What it can't do yet (straight, not undersold)

- **It types entities; it doesn't understand novel ones.** For entity *identity* it relies on reference packages (countries, world regions, currencies) — a very large but finite set. Programme names, agency names, and occupations have no offline canonical source; those are handled as text or need a reference you supply.
- **Meaning-based matching ("Provisions ~ Groceries") is optional and needs a download.** Reliable semantic similarity uses sentence-transformer embeddings, whose weights download once on your machine. Without them, matching is high-quality string / entity matching, not true synonymy.
- **Name intelligence and NER are optional add-ons.** Gender-from-name and person / organisation / place typing come from optional models / datasets you install once; the base engine runs without them.
- **Some calls are genuinely yours to make.** When a date column is fully ambiguous (every part <= 12), or a "same thing?" group is really two things, the tool asks rather than guesses. That's by design, not a gap.
- **Column split / merge (schema changes) is recorded, not auto-applied.** Reshaping that changes the table's shape is proposed and logged; value-level cleaning is applied on export.

## The interface (secondary)

Clean, sequential, calm. One decision per screen, two choices where possible. A light left rail shows where you are (Sign in -> Sector -> Upload -> Review -> Export). Formatting-only tidies collapse into a single accept. Merge suggestions are compact with a "split into sets" option when a group is really several things. Minimal formatting, short copy, no jargon — designed so a non-developer can run it end to end.

---

> **Everything above this line is written for everyone — funders, partners, and non-technical readers.** It's the complete picture of what the tool does, what it does well, and what it can't do yet. The sections below are for engineers and technical reviewers.

---

## Technical overview

### Architecture

```
file -> ingest -> profile (type inference) -> plan -> run_plan -> review -> export
                     |                                   |
         column-context inference             per-column transforms
      (date order, decimal convention,        (deterministic, reversible,
       entity domain, leading zeros)           consent-gated on export)
```

- **Deterministic core, optional intelligence.** The engine is rule-based and local. Machine learning and NLP are *optional layers* that rescue hard cases when installed; nothing core depends on a downloaded model.
- **Generic by design.** The plan is derived from inferred types, not a known schema. Region / entity data are swappable packs, never hard-coded assumptions. Nigeria is a pack, not the core.

### Engine (`engine/`)

- `ingest.py` — reads CSV / TSV / TXT (encoding + delimiter + header sniffing), Excel (multi-sheet), JSON, PDF tables; detects and reports banner rows; strips BOM / zero-width from headers.
- `profile.py` — semantic type inference with column-context passes: `infer_date_order` (51% majority), `infer_decimal_convention` (dot vs comma), leading-zero and alphanumeric-code detection, optional ML / NER rescue.
- `transforms/` — 23 registered transforms (numeric, dates / datetimes with impossible-date flagging, phones, emails, names with hyphen / O' / Mc handling, booleans, gender, coordinates, units, sentinels, range checks, categorical induction, resolve).
- `domains/` — package-based entity resolution: `country_converter` for countries, `pycountry` for currencies and 5,046 world subdivisions, small JSON for survey categoricals (sex, relationship-to-head, disability, payment channel, ID type). Powers merge-safety via `same_entity`.
- `ng_admin.py` — validation against the complete official set of Nigerian administrative units (36 states + FCT, 774 LGAs, from an MIT-licensed dataset). Typo-tolerant resolution (`rapidfuzz`, full-string ratio so short names don't false-match), plus level-mismatch and unknown-value flags surfaced as a review card.
- `dedupe.py` / `induce.py` — graded similarity clustering and meaning-preserving category induction; different numbers and different canonical entities never merge.
- `nlp/` — optional spaCy NER for column typing (person / org / place / money / date).
- `embeddings.py` — pluggable semantic-embedding layer with graceful fallback (sentence-transformers -> model2vec -> deterministic lexical vectors). Widens match RECALL for category merging and value synonymy; identity is still decided by the reference layer and user confirmation, never by embeddings alone. Reports the active backend honestly and runs everywhere, model or not.
- `names.py` — optional `names-dataset` layer for name recognition and probabilistic gender estimation.
- `pipeline.py`, `review.py`, `exporters.py`, `reshape.py`, `regions/`, `ml/` — plan execution, per-column change overview, CSV / XLSX / DOCX export, reshaping, region packs, trained type classifier.

### Reliability

~78 tests across 14 suites, including a `test_best_practices.py` battery that locks in the hard cases (unicode / zero-width, mojibake, leading-zero codes, impossible dates, hyphenated names, decimal-convention and date-order inference, "-1 != 1", BOM headers, account / age typing, and Nigerian state / LGA resolution with wrong-level flags).

```bash
for t in tests/*.py; do python "$t"; done
```

### Install

```bash
pip install -e .                 # core engine
pip install -e ".[web]"          # + FastAPI server
pip install -e ".[nlp]"          # + spaCy NER model (optional)
pip install -e ".[names]"        # + Nigerian-name / gender dataset (optional)
pip install -e ".[semantic]"     # + sentence-transformer embeddings (optional)
```

Reference packages (`country_converter`, `pycountry`) install with the core and work fully offline. Optional model / dataset weights download once from public package sources.

### Run

```bash
uvicorn app.server:app --reload        # web wizard at http://localhost:8000
```

The hosted demo (`one864prep-demo.onrender.com`) is synthetic-data-only, since hosting sends data to a server. The desktop build keeps all data on-device — that is the private one.

### Packages, and what each does here

The tool stands on established, well-maintained libraries rather than bespoke per-file rules. Attribution and role:

**Reading and repair**
- `pandas`, `numpy` — dataframes and vectorised operations throughout.
- `openpyxl` — reads and writes Excel (multi-sheet ingest, XLSX export).
- `pdfplumber` — extracts tables from PDFs.
- `charset-normalizer` — detects file encoding so non-UTF-8 files read correctly.
- `ftfy` — repairs mojibake (`Ã©cole -> école`) and broken unicode.
- `langdetect` — language hint for text columns.

**Type-specific cleaning**
- `python-dateutil`, `dateparser` — parse dates in many human formats; `dateparser` respects the column-level order we infer.
- `phonenumbers` — Google's libphonenumber port; validates and formats phone numbers to a standard.
- `email-validator` — validates and normalises email addresses.
- `price-parser`, `babel` — currency and locale-aware number handling (with our own decimal-convention layer on top; see below).
- `pint` — unit parsing and conversion (`3200g` -> `3.2kg`).
- `lat-lon-parser` — parses coordinates in decimal and DMS forms, preserving precision.

**Matching, entities, dedup**
- `rapidfuzz` — fast fuzzy string similarity for graded duplicate clustering.
- `jellyfish` — phonetic matching (Soundex/Metaphone) for name-like variants.
- `country_converter` — harmonises country names across ISO / UN / World Bank conventions to ISO3 codes. This is what makes `Congo, Dem. Rep.` and `Congo, Rep.` distinct while `naija -> Nigeria` resolves.
- `pycountry` — authoritative offline ISO data: currencies and 5,046 world subdivisions (states, provinces, counties, LGAs), so look-alike regions never merge.

**Machine learning / NLP (optional)**
- `scikit-learn`, `joblib` — the trained column-type classifier that rescues hard-to-type columns.
- `spacy` + `en_core_web_md` (optional `[nlp]`) — NER for column typing (person / org / place / money / date); downloads once from GitHub.
- `names-dataset` (optional `[names]`) — large offline global names dataset covering Nigerian names; powers name recognition and probabilistic gender estimation.
- `sentence-transformers` (optional `[semantic]`) — meaning-based similarity for the free-text long tail; weights download once.

**Serving and packaging**
- `fastapi`, `uvicorn`, `python-multipart` (`[web]`) — the local web wizard.
- `python-docx` — Word report / change-log export.
- `pywebview`, `pyinstaller` (`[desktop]`) — the on-device desktop build.

### Engineering decisions that make it better

The non-obvious choices, and why they matter:

- **Validate against the known universe, don't just clean.** For any column with a finite correct set (administrative regions, currencies, standard categories), the engine resolves each value against the full official list: near-misses become one-tap corrections, wrong-level entries and values outside the set are flagged for review. This turns cleaning into a data-quality check, and it's the same mechanism across every closed-set column, not a per-column special case.
- **Reference-first, embeddings-assist.** For deciding whether two entries are the *same real-world thing*, we match against authoritative reference data before reaching for similarity or embeddings. A neural model places near-identical-looking labels close together and merges things that shouldn't merge; a reference source keeps genuinely distinct entries distinct. Embeddings are reserved for the genuinely fuzzy free-text tail, not for facts a reference already settles.
- **Column-context inference before per-value cleaning.** Some formats are undecidable from a single value but obvious across the column. We do a pre-pass that infers date order (51% majority, so one typo can't flip it) and decimal convention (dot vs comma) from the whole column, then clean every value consistently. This is what prevents both the month/day swap and the `42.959 -> 42959` corruption.
- **Value identity over string shape.** Numbers are compared by value, not by digits: `-1` and `1` are different (one is a sentinel), while `7.0` and `7` are the same. This single rule stops a whole class of silent category corruption.
- **Meaning-preserving category induction.** Categories merge only when they are genuinely the same (case, spacing, `&` vs `and`, word order) — never across different words or different numbers. Ranges like `1-5` and `6-10` never collapse.
- **Flag, don't fix, when meaning is at stake.** Impossible dates, out-of-range values, and sentinels are surfaced for review, never silently coerced. A single stray outlier is treated as a possible typo, not a signal to reinterpret the whole column.
- **Batch the harmless, foreground the meaningful.** Formatting-only changes (spacing, case) are grouped into one "accept all" screen with an honest "this does not change meaning" note; only decisions that alter meaning cost you a card. Review time is spent where judgement is actually needed.
- **Detect-and-show, never silent drop.** Banner / caption rows are detected and displayed with exactly what was skipped; the header is found automatically but the cut is always visible and reversible.
- **Honest UX as a feature.** Progress reflects real per-column work and never claims completion early. When something is genuinely ambiguous (a date column where every part is <= 12, or a group that is really two things), the tool asks instead of guessing.
- **Optional intelligence, never a hard dependency.** Every model / dataset layer degrades to nothing when absent. The deterministic engine always runs; the repo stays small because model weights are pulled on demand, not shipped.
- **Nigeria is a pack, not the core.** Region and entity data are swappable. The same engine cleans a Kenyan county roll or a global fragile-states index without code changes.

### Design principles (non-negotiable)

1. Generic and robust across sectors and countries; built on established packages, not bespoke per-file rules.
2. Never alter data to mean something else; consent before any change.
3. AI is an optional enhancement, not the core.
4. Simple, sequential, uncluttered interface.
5. Honest about limits and trade-offs.

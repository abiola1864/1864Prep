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

| The quiet problem | What 1864 Prep does |
| --- | --- |
| A value's format is unreadable on its own (`12.05.2021` — May or December? `42.959` — decimal or thousands?) | Reads the **whole column** first, locks one layout for every row (51% majority, so one typo can't flip it), and never turns `42.959` into `42959` |
| Codes that only look like numbers (`007`, `01234`, account numbers) | Keeps them as codes so leading zeros survive; never confuses a code column with a phone or a measurement |
| Not all changes are equal — spacing vs. merging entries | Applies safe formatting (spacing, case) automatically and only asks you about changes that alter meaning |
| Tools "correcting" bad data into wrong data | Flags impossible dates, out-of-range values, and refusal codes (`999`, `-1`) instead of fixing them; merges two values only when they genuinely mean the same thing |
| Invisible corruption (zero-width characters, BOMs, `Ã©` that should be `é`) and unknown file encodings | Cleans these everywhere and reads any encoding (UTF-16, UTF-8-BOM, …) so a mangled export still opens |
| Excel leaking dates as bare numbers like `44562`, even as column headings | Restores the real date, while leaving genuine ID and code numbers untouched |
| Cleaned files that then break the next tool ("EOF within quoted string") | Strips in-field line breaks and control characters so the file opens cleanly, with meaning unchanged |
| A title, source line, or blank rows sitting above the real table | Finds the true header and shows you exactly what sat above it — never dropped silently |
| Real-world things, not just text (people, places, money, regions, currencies) | Identifies what a column actually holds and standardises to the proper form, the same on a health roll, an agriculture registry, or a global index |
| Values that should belong to a known set (regions, currencies, categories) | Checks each against the full official list: near-misses become one-tap corrections, wrong-level and unknown values are flagged for you — nothing changed silently |
| Dishonest progress bars and silent guesses | Progress reflects real per-column work; when something is genuinely ambiguous, it asks instead of guessing |

## What it can't do yet (straight, not undersold)

| Limitation | What that means |
| --- | --- |
| Types entities, doesn't understand novel ones | Identity relies on reference sets (countries, world regions, currencies) — large but finite. Programme names, agency names, occupations are handled as text or need a reference you supply |
| Meaning-based matching is optional | "Provisions ≈ Groceries" needs sentence-transformer embeddings that download once on your machine; without them, matching is strong string / entity matching, not true synonymy |
| Name and entity intelligence are add-ons | Gender-from-name and person / organisation / place typing come from optional models you install once; the base engine runs without them |
| Some calls are genuinely yours | A fully ambiguous date column (every part ≤ 12) or a "same thing?" group that is really two things is surfaced for you, by design |
| Schema reshaping is recorded, not auto-applied | Column split / merge that changes the table's shape is proposed and logged; value-level cleaning is applied on export |


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

| Module | Responsibility |
| --- | --- |
| `ingest.py` | Reads CSV / TSV / TXT (BOM-first encoding for UTF-16 / UTF-8-BOM with latin-1 fallback, delimiter + header sniffing), Excel (multi-sheet), JSON, PDF tables; reports banner rows; strips BOM / zero-width; repairs Excel date-serials leaked into headers |
| `profile.py` | Semantic type inference with column-context passes: `infer_date_order` (51% majority), `infer_decimal_convention` (dot vs comma), leading-zero and alphanumeric-code detection, optional ML / NER rescue |
| `transforms/` | 23 transforms: numeric, dates / datetimes with impossible-date flagging, phones, emails, names (hyphen / O' / Mc), booleans, gender, coordinates, units, sentinels, range checks, category induction, resolve |
| `domains/` | Reference-based entity resolution — `country_converter` for countries, `pycountry` for currencies and 5,046 world subdivisions, JSON for survey categoricals; powers merge-safety via `same_entity` |
| `ng_admin.py` | Validation against the full official set of Nigerian admin units (36 states + FCT, 774 LGAs, MIT-licensed). Typo-tolerant resolution, plus level-mismatch and unknown-value flags |
| `dedupe.py` / `induce.py` | Graded similarity clustering and meaning-preserving category induction; different numbers and canonical entities never merge |
| `embeddings.py` | Pluggable semantic layer (sentence-transformers → model2vec → deterministic lexical fallback). Widens match *recall*; identity stays with the reference layer. Reports its active backend honestly, runs everywhere |
| `nlp/` | Optional spaCy NER for column typing (person / org / place / money / date) |
| `names.py` | Optional `names-dataset` layer for name recognition and probabilistic gender estimation |
| `exporters.py` | CSV / XLSX / DOCX output; CSV is made safe for downstream tools (in-field line breaks and control characters removed, meaning unchanged) |
| `pipeline.py`, `review.py`, `reshape.py`, `regions/`, `ml/` | Plan execution, per-column change overview, reshaping, swappable region packs, trained type classifier |

### Reliability

~85 tests across 16 suites, including a `test_best_practices.py` battery that locks in the hard cases (unicode / zero-width, mojibake, leading-zero codes, impossible dates, hyphenated names, decimal-convention and date-order inference, "-1 != 1", BOM headers, account / age typing, Nigerian state / LGA resolution with wrong-level flags, Excel date-serials, and export-safety).

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

The tool stands on established, well-maintained libraries rather than bespoke per-file rules.

| Area | Package | What it does here |
| --- | --- | --- |
| Reading & repair | `pandas`, `numpy` | Dataframes and vectorised operations throughout |
| | `openpyxl` | Reads and writes Excel (multi-sheet ingest, XLSX export) |
| | `pdfplumber` | Extracts tables from PDFs |
| | `charset-normalizer` | Detects file encoding so non-UTF-8 files read correctly |
| | `ftfy` | Repairs mojibake (`Ã©cole → école`) and broken unicode |
| | `langdetect` | Language hint for text columns |
| Type-specific cleaning | `python-dateutil`, `dateparser` | Parse dates in many human formats; respect the column-level order we infer |
| | `phonenumbers` | Google's libphonenumber port; validates and formats phone numbers |
| | `email-validator` | Validates and normalises email addresses |
| | `price-parser`, `babel` | Currency and locale-aware number handling (with our own decimal-convention layer on top) |
| | `pint` | Unit parsing and conversion (`3200g → 3.2kg`) |
| | `lat-lon-parser` | Parses coordinates in decimal and DMS forms, preserving precision |
| Matching & entities | `rapidfuzz` | Fast fuzzy string similarity for graded duplicate clustering and typo tolerance |
| | `jellyfish` | Phonetic matching (Soundex / Metaphone) for name-like variants |
| | `country_converter` | Harmonises country names (ISO / UN / World Bank) to ISO3, so look-alike countries stay distinct while true variants resolve |
| | `pycountry` | Authoritative offline ISO data: currencies and 5,046 world subdivisions |
| ML / NLP (optional) | `scikit-learn`, `joblib` | Trained column-type classifier that rescues hard-to-type columns |
| | `spacy` + `en_core_web_md` `[nlp]` | NER for column typing (person / org / place / money / date) |
| | `names-dataset` `[names]` | Large offline global names dataset; name recognition and probabilistic gender estimation |
| | `sentence-transformers`, `model2vec` `[semantic]` | Meaning-based similarity for the free-text long tail; weights download once |
| Serving & packaging | `fastapi`, `uvicorn`, `python-multipart` `[web]` | The local web wizard |
| | `python-docx` | Word report / change-log export |
| | `pywebview`, `pyinstaller` `[desktop]` | The on-device desktop build |

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

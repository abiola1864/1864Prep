# 1864 Prep

A local tool that standardises messy government and survey data, so verified answers can join an open network without the raw data leaving your computer.

Built by the 1864 Research and Innovation Institute for real field data: household surveys, farmer registries, social-protection rolls, and cross-country indices. It reads CSV, Excel, JSON, and PDF tables, works out what each column contains, proposes clean-ups you approve, and produces a tidy file plus a full change log.

Two things it always does:

1. Your data stays on your computer. The engine runs locally. The hosted demo uses synthetic data only; the desktop build keeps everything on-device.
2. It never changes the meaning of a value without your approval. Formatting that does not change meaning (spacing, capitalisation) is applied automatically and listed for you; anything else is a proposal you accept or reject.

The first half of this page is written for any reader and needs no technical background. The technical reference follows the divider.

## What it does

The most important behaviours are listed first.

| Feature | What it does |
| --- | --- |
| Reads the whole column before deciding a format | Decides date order and decimal style from the full column, not one cell. `12.05.2021` is read the same way for every row, and `42.959` stays `42.959` instead of becoming `42959`. A single typo cannot flip the format. |
| Checks values against a known-correct list | For regions, currencies, and standard categories, each value is checked against the official list. A near miss (a mistyped place name) becomes a one-tap correction; a value at the wrong level (a state entered where a local area belongs) or one that is not on the list at all (a town entered as a local area) is flagged for you. |
| Recognises real-world things, not just text | Identifies people, places, organisations, money, dates, regions, and currencies, and standardises them to a consistent form. The same engine works on a health roll, an agriculture registry, or a global index. |
| Keeps codes separate from numbers | `007`, `01234`, and account numbers stay as codes with their leading zeros, rather than the numbers 7 and 1234. A code column is never treated as a phone number or a measurement. |
| Separates safe changes from meaning changes | Spacing and capitalisation are applied automatically, with a list of exactly what changed. Anything that changes meaning is shown for your approval, one decision at a time. |
| Flags bad data instead of guessing | Impossible dates (`2024-13-99`), out-of-range values, and placeholder codes like `999` or `-1` are flagged, not overwritten. Two values are merged only when they genuinely mean the same thing. |
| Restores Excel date serials | A cell or column heading showing `44562` becomes `2022-01-01`. Genuine ID and code numbers are left unchanged. |
| Cleans hidden characters and any encoding | Removes zero-width characters, non-breaking spaces, and byte-order marks, repairs garbled text (`Ã©` becomes `é`), and reads files in any encoding, including UTF-16, so a damaged export still opens. |
| Finds the real table in a messy file | Skips a title, source line, logo, or blank rows above the data, finds the true header row, and shows you what sat above it. |
| Produces files that open cleanly elsewhere | Removes in-field line breaks and control characters that otherwise break spreadsheets and dashboards. Values keep their meaning. |
| Finds duplicate rows and repeated columns | Flags rows that exactly repeat another row and columns that hold the same field under different names, and removes duplicates on request while keeping one of each. |
| Standardises common fields | Phone numbers to one format, email addresses lowercased, dates to `YYYY-MM-DD`, numbers without currency symbols or thousands separators, and consistent name capitalisation (including hyphens, `O'` and `Mc`). |
| Shows accurate progress | The progress bar reflects the real work happening column by column and only reaches 100% when the file is ready. |
| Exports the result and an audit trail | CSV, Excel, or Word, plus a change log of every accepted change. |
| Includes a Data Toolkit | One-off jobs: find duplicates, find outliers, match two files, validate, summarise, compare, combine, anonymise, quick-clean a whole file, and estimate gender from a name. |

## Optional add-ons

These are off by default and installed once. The core engine runs without them.

| Add-on | What it adds |
| --- | --- |
| AI assistance | Uses a model you connect to help with the hardest columns. Off by default. |
| Named-entity recognition (spaCy) | Helps type columns as person, organisation, place, money, or date. |
| Name and gender dataset | Recognises personal names, including Nigerian names, and gives a labelled gender estimate that is left blank for unisex names. |
| Meaning-based matching | Matches values that mean the same thing but are spelled differently (for example "Provisions" and "Groceries"). Without it, matching is based on spelling and reference lists. |

## Notes on scope

| Area | Detail |
| --- | --- |
| Entity identity | Uses reference sets (countries, world regions, currencies). These are large but finite. Programme names, agency names, and occupations are treated as text unless you supply a reference list. |
| Ambiguous cases | When a date column has every part 12 or below, or a group of values could be one thing or several, the tool asks rather than guessing. |
| Column split and merge | Changes to the shape of the table are recorded and applied at export; value-level cleaning is applied directly. |

## The interface

The wizard is sequential and plain: one decision per screen, two choices where possible. A top bar shows where you are (sign in, data type, upload, column names, review, done). Formatting-only tidying is applied automatically and summarised, with an option to see exactly what changed. Copy is written in everyday language with no jargon, so a non-technical user can run it start to finish.

---

## Technical overview

### Architecture

```
file -> ingest -> profile (type inference) -> plan -> run_plan -> review -> export
                     |                                   |
         column-context inference             per-column transforms
      (date order, decimal style,             (deterministic, reversible,
       entity domain, leading zeros)           applied on export)
```

The engine is rule-based and runs locally. Machine learning and NLP are optional layers that improve hard cases when installed; nothing in the core depends on a downloaded model. The plan is derived from inferred types rather than a fixed schema, and region and entity data are swappable packs, so the same engine works across sectors and countries.

### Engine (`engine/`)

| Module | Responsibility |
| --- | --- |
| `ingest.py` | Reads CSV, TSV, TXT (BOM-first encoding for UTF-16 and UTF-8-BOM with a latin-1 fallback, delimiter and header sniffing), Excel (multi-sheet), JSON, and PDF tables; reports banner rows; strips BOM and zero-width characters; repairs Excel date-serials leaked into headers. |
| `profile.py` | Type inference with column-context passes: `infer_date_order` (51% majority), `infer_decimal_convention` (dot vs comma), leading-zero and alphanumeric-code detection, optional ML and NER rescue. |
| `transforms/` | 23 transforms: numeric, dates and datetimes with impossible-date flagging, phones, emails, names, booleans, gender, coordinates, units, placeholder codes, range checks, category induction, and reference resolution. |
| `domains/` | Reference-based entity resolution: `country_converter` for countries, `pycountry` for currencies and 5,046 world subdivisions, JSON for survey categories. Provides merge-safety via `same_entity`. |
| `ng_admin.py` | Validation against the full official set of Nigerian administrative units (36 states plus FCT, 774 LGAs). Typo-tolerant resolution, plus level-mismatch and unknown-value flags. |
| `dedupe.py`, `induce.py` | Duplicate detection and meaning-preserving category grouping. Different numbers and different reference entities never merge. |
| `embeddings.py` | Pluggable semantic layer (sentence-transformers, then model2vec, then a deterministic lexical fallback). Widens match recall; identity stays with the reference layer. Reports its active backend and runs with or without a model. |
| `nlp/` | Optional spaCy NER for column typing. |
| `names.py` | Optional `names-dataset` layer for name recognition and gender estimation. |
| `exporters.py` | CSV, XLSX, and DOCX output. CSV output removes in-field line breaks and control characters so the file opens cleanly elsewhere. |
| `pipeline.py`, `review.py`, `reshape.py`, `regions/`, `ml/` | Plan execution, per-column change overview, reshaping, region packs, and the trained type classifier. |

### Reliability

About 85 tests across 16 suites, including a `test_best_practices.py` set that covers unicode and zero-width handling, garbled text repair, leading-zero codes, impossible dates, hyphenated names, decimal-style and date-order inference, keeping different numbers apart, BOM headers, account and age typing, Nigerian state and LGA resolution with wrong-level flags, Excel date-serials, and export safety.

```bash
for t in tests/*.py; do python "$t"; done
```

### Install

```bash
pip install -e .                 # core engine
pip install -e ".[web]"          # FastAPI server
pip install -e ".[nlp]"          # spaCy NER model
pip install -e ".[names]"        # name and gender dataset
pip install -e ".[semantic]"     # sentence-transformer embeddings
```

The core packages install and run fully offline. Optional model and dataset weights download once from public package sources.

### Run

```bash
uvicorn app.server:app --reload        # web wizard at http://localhost:8000
```

The hosted demo at `one864prep-demo.onrender.com` uses synthetic data only, since hosting sends data to a server. The desktop build keeps all data on-device.

### Packages

| Area | Package | What it does here |
| --- | --- | --- |
| Reading and repair | `pandas`, `numpy` | Dataframes and vectorised operations. |
| | `openpyxl` | Reads and writes Excel. |
| | `pdfplumber` | Extracts tables from PDFs. |
| | `charset-normalizer` | Detects file encoding. |
| | `ftfy` | Repairs garbled text and broken unicode. |
| | `langdetect` | Language hint for text columns. |
| Field cleaning | `python-dateutil`, `dateparser` | Parse dates in many formats, respecting the column order the engine infers. |
| | `phonenumbers` | Validates and formats phone numbers. |
| | `email-validator` | Validates and normalises email addresses. |
| | `price-parser`, `babel` | Currency and locale-aware number handling. |
| | `pint` | Unit parsing and conversion (`3200g` to `3.2kg`). |
| | `lat-lon-parser` | Parses coordinates in decimal and DMS forms. |
| Matching and entities | `rapidfuzz` | Fast fuzzy similarity for duplicate clustering and typo tolerance. |
| | `jellyfish` | Phonetic matching for name-like variants. |
| | `country_converter` | Harmonises country names (ISO, UN, World Bank) to ISO3 codes. |
| | `pycountry` | Offline ISO data: currencies and 5,046 world subdivisions. |
| ML and NLP (optional) | `scikit-learn`, `joblib` | Trained column-type classifier. |
| | `spacy` with `en_core_web_md` `[nlp]` | Named-entity recognition for column typing. |
| | `names-dataset` `[names]` | Name recognition and gender estimation. |
| | `sentence-transformers`, `model2vec` `[semantic]` | Meaning-based matching. |
| Serving and packaging | `fastapi`, `uvicorn`, `python-multipart` `[web]` | The local web wizard. |
| | `python-docx` | Word report and change-log export. |
| | `pywebview`, `pyinstaller` `[desktop]` | The on-device desktop build. |

### Engineering decisions

| Decision | Reason |
| --- | --- |
| Validate against a known set, not only clean formatting | For any column with a finite correct set, each value is resolved against the full list, so near misses become corrections and out-of-set values are flagged. The same mechanism is used for every closed-set column. |
| Reference first, embeddings second | Identity is decided by reference data before similarity or embeddings, so labels that look alike but differ stay distinct. Embeddings are used only for open-ended free text. |
| Read the whole column before cleaning a value | Date order and decimal style are inferred from the column, then applied consistently. This prevents both month/day swaps and turning `42.959` into `42959`. |
| Compare numbers by value | `-1` and `1` are different (one is a placeholder), while `7.0` and `7` are the same. This prevents a class of silent corruption. |
| Flag, do not fix, when meaning is at stake | Impossible dates, out-of-range values, and placeholder codes are surfaced for review rather than changed. |
| Apply the safe changes, ask about the rest | Formatting-only changes are applied automatically and listed; only meaning-changing decisions require input. |
| Detect and show, never drop silently | Banner rows and skipped content are shown, not removed without notice. |
| Optional intelligence, never a hard dependency | Every model and dataset layer degrades to nothing when absent; the deterministic engine always runs and the repository stays small. |
| Regions are swappable packs | Region and entity data are packs, so the same engine cleans data from any country without code changes. |

### Design principles

1. Generic and robust across sectors and countries, built on established packages rather than per-file rules.
2. Never change the meaning of a value without approval.
3. AI is an optional enhancement, not the core.
4. A simple, sequential, uncluttered interface.
5. Clear about scope and trade-offs.

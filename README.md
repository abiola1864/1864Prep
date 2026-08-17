# 1864 Prep

**Turn any messy government or survey file into clean, trustworthy, shareable data — on your own computer, with every change shown for approval.**

1864 Prep is a local, open-source tool built by the 1864 Research and Innovation Institute. It reads whatever an agency actually has — CSV, Excel (`.xlsx` and legacy `.xls`), JSON, even tables inside PDFs — works out what each column means, proposes clean-ups you approve one at a time, and produces a tidy file plus a complete change log. It is the groundwork that lets verified answers travel across an open data network without the raw records ever leaving your machine.

Two promises hold everywhere in the tool:

1. **Your data stays with you.** The engine runs locally; nothing is uploaded. The hosted demo uses synthetic data only, and the optional AI assist (below) is off by default.
2. **Meaning is never changed without your sign-off.** Safe formatting (spacing, capitalisation) is applied and listed for you; anything that could change meaning is a proposal you accept or reject, and every decision is recorded.

The first half of this page needs no technical background. The technical reference follows the divider.

---

## What it does

The intelligent work and the dependable groundwork, in plain terms.

### The intelligent part — reading messy data like an analyst

The smart work that turns whatever an agency has into data that can actually be used and shared.

| Capability | Method | What it does |
| --- | --- | --- |
| **Interprets what each data point means** | Machine learning | Works out on its own whether a field is a date, a name, an amount, or a code. |
| **Finds relevant information in free text** | Named-entity recognition | Finds people, places, organisations, and money inside free-text fields. |
| **Reads most files and fragmented headers** | Format parsing | CSV, Excel (`.xlsx`/`.xls`), JSON, PDF tables — in any encoding, even multi-row and merged headers. |
| **Fixes mismatched but identical labels** | Embeddings | Links categories and labels that are spelled differently but mean the same thing. |
| **Matches irregular values to official registers** | Reference matching | Matches entries to the correct official name (states, local areas, countries, currencies) and suggests the fix. |

### The dependable part — groundwork that makes the data trustworthy

The reliable cleaning underneath, applied consistently, and never without a person's sign-off.

| Capability | Method | What it does |
| --- | --- | --- |
| **Standardises dates and numbers** | Rule-based transforms | One format for dates, numbers, phones, and emails across the whole file. |
| **Repairs encoding and date errors** | Unicode repair | Recovers scrambled text (`Ã©` → `é`) and Excel date-serials (`44562` → `2022-01-01`) that other tools miss. |
| **Preserves ID and account numbers** | Type inference | Keeps leading zeros and long IDs intact — the key to matching records across agencies. |
| **Flags duplicates and outliers** | Fuzzy matching | Catches repeated rows and impossible values, and asks before acting. |
| **Logs every change for approval** | Human-in-the-loop | Nothing is altered without a person's sign-off, and all of it is recorded. |

### Understanding the table first

Before any value is touched, 1864 Prep works out the **structure** of the file:

- **Finds the real table** in a messy sheet — skips titles, source lines, logos, and blank rows above the data, and reports what sat above the header.
- **Resolves multi-row and merged headers** — reads the actual merged-cell ranges from Excel and composes a single clear name per column (a group label like "Children under 1" over "Value" becomes one readable heading), instead of leaving blanks or duplicates.
- **Picks the right sheet** in a multi-sheet workbook — prefers the clean primary table and skips helper sheets ("check", "notes", "pivot"), and processes **every sheet independently**, keeping each sheet's name and structure rather than merging them into one.
- **Reads the whole column before deciding** its type and format, so one odd cell cannot flip the interpretation of the rest.
- **Reports filters and frozen panes** (view-only settings that never change your values) for transparency.

### A whole toolkit, one click each

Beyond the guided wizard, a set of one-off tools — each now with its **own step-by-step workflow** rather than a single generic run:

| Tool | Its workflow |
| --- | --- |
| **Find outliers** | Clean → pick numeric columns → **see the spread** → choose method (IQR vs Z-score) → **review flagged** → decide keep / cap / remove → export |
| **Find duplicates** | Clean → pick match columns → **check confusing columns** → exact vs near → review each group → choose which to keep → export |
| **Validate data** | Clean → pick required fields → set rules → review issues → export report |
| **Match & merge files** | Add files → clean → confirm shared key → choose join type → preview → export |
| **Anonymise / mask** | Clean → pick sensitive columns → choose hash / mask / drop → preview before/after → export |
| **Summarise / profile** | Clean → pick columns → choose summary → view & export |
| **Compare two files** | Add old & new → clean → confirm row key → choose focus → review differences → export |
| **Combine / append** | Add files → check columns align → preview → export |
| **Remove duplicates** | Clean → pick keys → confusion check → keep-rule → preview → export |
| **Estimate gender from a name** | Clean → pick the name column → confirm (opt-in) → preview → export |
| **Quick clean (whole file)** | Deliberately one click, by design |

### See your distribution — before and after

For any numeric column, 1864 Prep can show the **shape of your data**: an interactive histogram, the mean and median, and flagged outliers. It does this on both the raw and the cleaned data, so you can see, side by side, what cleaning recovered — "this is what you had, and this is what it became."

---

## Technical reference

### Install and run

```bash
pip install -e .            # core engine (pandas, openpyxl, xlrd)
uvicorn app.server:app --reload
# open http://localhost:8000
```

Optional extras (off by default, installed once):

```bash
pip install -e ".[nlp]"        # spaCy named-entity recognition
pip install -e ".[semantic]"   # sentence-transformer embeddings for label matching
pip install -e ".[names]"      # names dataset for gender estimation
pip install -e ".[web]"        # FastAPI + uvicorn if not already present
```

### Architecture

```
engine/
  ingest.py        file reading; sheet selection; multi-row & merged-header
                   resolution; banner skipping; encoding & delimiter sniffing
  headers.py       header normalisation — proposes a clean, readable name for
                   every column and flags abnormal ones (blank, generic, serial)
  profile.py       per-column type inference (date, number, code, boolean,
                   gender, email, phone, geo, currency, category, free text)
  transforms/      23 rule-based, consent-first value transforms
  domains/         official reference data (countries, currencies, subdivisions)
  dedupe.py        safe near-duplicate detection
  embeddings.py    meaning-based label matching (with graceful fallbacks)
  distribution.py  chart-ready distributions + before/after reveal
  flows.py         per-tool, human-centred step sequences
  toolkit.py       the one-off tools + outlier_evaluate / dedupe_confusion
  exporters.py     CSV / XLSX (single & multi-sheet) / DOCX + change log

app/
  server.py        FastAPI endpoints
  ui/              shared front-end (incl. delight.css / delight.js animations)
```

### Key API endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /api/profile` | Read a file; return column types + proposed header names |
| `POST /api/clean` / `POST /api/clean_stream` | Full clean with a reviewable worklist of every decision |
| `GET  /api/tool/{name}/flow` | The tool's own ordered steps |
| `POST /api/tool/outliers/evaluate` | Per-column distribution read-out (the "see the spread" step) |
| `POST /api/tool/duplicates/confusion` | Warn about inconsistent match columns before finalising |
| `POST /api/distribution` | Distribution for one dataset, or a before/after pair |
| `GET  /api/ai/status`, `POST /api/ai/preview` | AI-assist online/offline switch and safe per-column preview |
| `POST /api/export` | CSV / Excel / Word + change log |

### Privacy-preserving AI assist (optional)

The base tool is fully offline. If a key is present **and** the user turns it on, an optional AI assist can help name or categorise a tricky column. It is built so the model never sees the dataset:

- It works **one column at a time**, sending only a few **distinct** sample values (never full rows, never row counts).
- Sensitive columns (phone, ID, name, account…) are **masked to their shape** (`08031234567` → `99999999999`) or reduced to a pattern (`[11 digits]`), or nothing is sent at all.
- The interface shows a clear **online/offline switch** and can **preview exactly what would be sent** before anything leaves the device.

### Testing

```bash
for t in tests/*.py; do [ "$(basename $t)" = benchmark.py ] || PYTHONPATH=. python "$t"; done
```

Around 20 test suites cover ingestion, header resolution, type inference, the transforms, the domains, dedupe, embeddings, the per-tool flows, and the distribution engine.

---

Built by the **1864 Research and Innovation Institute**. Open source — contributions and issues welcome.

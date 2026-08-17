# 1864 Prep — the optimized pipeline

One path the engine always follows, for **any** file structure. Two ideas run
through the whole thing:

- **Context flows forward.** Nothing is cleaned in isolation. Each stage adds to
  a shared understanding — what this dataset is, what each column means, what
  values it should hold — and later stages use it.
- **Every decision is shown.** The engine proposes; the person disposes. Safe
  formatting is applied and listed; anything that could change meaning waits for a
  sign-off. Every decision, taken or pending, appears in the review and the log.

```
 SOURCE ─▶ 0 Intake ─▶ 1 Structure ─▶ 2 Column identity ─▶ 3 Header review
                                                                   │
        8 Export ◀─ 7 Insight ◀─ 6 Apply & verify ◀─ 5 Decide ◀─ 4 Plan
```

Carried the whole way: a **Context** object (dataset-level + per-column) and a
**Decisions ledger** (every proposed/taken action, with before→after).

---

## The two things carried through every stage

### Context (accumulates, never resets)

```
Context
  dataset:
    source, file_type, encoding, sheet_name, sheets_all[]
    structure: banner_rows[], header_rows[], data_start, merges_filled,
               orientation, filters, frozen_panes, dropped_blank_cols[]
    domain_guess: e.g. "health roll", "budget form", "cross-country index"
  columns[]:                      one entry per column, filled progressively
    raw_header, proposed_name, confirmed_name
    semantic_type   (date | number | code | id | boolean | gender | email |
                     phone | geo | currency | category | name | free_text)
    expected:       { format?, allowed_set?, range?, pattern?, nullable? }
    evidence:       why the type was chosen (read from the WHOLE column)
    context_note:   what this column represents, in one line
```

### Decisions ledger (every decision, shown "severally")

```
Decision
  column, kind (rename | retype | reformat | reference_fix | repair |
                flag | merge | drop | dedupe | outlier)
  before  →  after            (a concrete sample, always)
  safety: "safe" (auto, listed) | "meaning" (needs approval)
  status: proposed | accepted | rejected | applied
  reason: plain-language why
```

Nothing reaches Export that is not in this ledger.

---

## Stage 0 — Intake  *(read the source as-is)*

**Goal:** get the raw grid without assuming anything.

- Detect file type; for text, sniff **encoding** (BOM/UTF-16 aware) and **delimiter**.
- For Excel, enumerate **all sheets**. For **each sheet independently** capture the
  raw grid *plus* structural metadata: **merged-cell ranges, auto-filter range,
  frozen panes**. Sheets are never merged into one.
- **Size guard:** for very large files, read in **chunks / streaming**, sample the
  first N rows for structure and typing, then process the rest in batches; support
  reading straight from a `.zip`. A hard cap with a clear message beats a crash.

**Shown:** file type, encoding, sheet list, size, and "reading in batches" when large.
**Context set:** `source, file_type, encoding, sheets_all`.

---

## Stage 1 — Structure understanding  *(the crux: what IS this table?)*

This is where most tools fail and where context matters most. Run **per sheet**.

1. **Un-merge:** fill every merged span from the real merged ranges, so a group
   label reaches every column it covers (not just the top-left cell).
2. **Find the data region:** the first row that looks like real data — several
   non-empty cells, a *mix* of text and numbers — confirmed by the row below.
   Everything above that is banner / title / notes.
3. **Find the header band:** the contiguous non-blank rows sitting just above the
   data start (skipping a blank separator). One row, or several stacked rows.
4. **Compose headers:** turn 1–3 stacked rows into **one clear name per column**,
   using the true merges (a "Children under 1" group over "Value" becomes one
   heading, not a blank or a duplicate).
5. **Decide orientation — headers must end up as columns (the y-axis of names).**
   Detect three shapes and normalise all to "headers across the top":
   - *Normal:* header row on top → keep.
   - *Transposed:* the first **column** holds the field names and rows hold records
     (values run left-to-right) → **transpose** so fields become columns.
   - *Form / template:* column A is a **category/label** column (e.g. "Travel",
     "Data Acquisition", "Sub-total"), not data — recognise it as a label column,
     don't mistake a section title for the header, and treat the sheet as a form
     needing explicit header confirmation.
6. **Drop fully-blank spacer rows and columns**, recorded.
7. **Pick the primary sheet** when one is needed: prefer the clean rectangular
   table, skip helper sheets ("check", "notes", "pivot"); but keep all sheets
   available and process each on its own.

**Shown (a structure card):** "Skipped 6 banner rows · header is rows 8–10, merged
into single names · filled 2 merged blocks · this looks like a *form* · dropped 2
blank columns · sheet *Birth registration* chosen (also: *check*)." The person can
**override** the header row, orientation, and sheet.
**Context set:** everything under `dataset.structure` + `domain_guess`.

---

## Stage 2 — Column identity & context  *(read the whole column, in context)*

For **each** column, using its header name **and** its full contents (never one cell):

- **Infer the semantic type** from the whole column: date, number, code, ID,
  boolean, gender, email, phone, geo, currency, category, name, free text.
- **Establish expected values** — the column's contract:
  - a **reference set** (states, local areas, countries, currencies) → allowed list;
  - a **range** (e.g. a percentage is 0–100);
  - a **format** (dates → one order; codes → keep leading zeros);
  - a **pattern** (email, phone);
  - whether blanks are acceptable.
- **Guard against look-alikes:** a code column (`007`) is not the number 7; a
  footnote flag (`y`, `y,v`) is not a boolean; an ID is not a phone number. Booleans
  require **both** poles present, not just `y`.
- **Write a one-line context note:** "looks like a Nigerian local-area column",
  "currency amount in GBP", "identifier — keep as text". This note drives the
  suggestions in later stages, including safe **merge** proposals.
- **Propose a readable name** for any abnormal header (blank, generic `Var2`, a
  leaked date-serial).

**Shown:** per-column card — proposed name, detected type, expected values, and the
evidence ("94% parse as dates in D/M/Y order").
**Context set:** each `columns[].semantic_type, expected, evidence, context_note`.

---

## Stage 3 — Header review  *(human-in-the-loop, and FIRST)*

Before a single value is cleaned, the person confirms the **structure and identity**:

- Accept or edit each **column name**.
- Accept or change each **detected type / expected values**.
- Confirm **orientation** and **which sheet(s)** to process.

Why first: if the columns are wrong, every downstream fix is wrong. Fixing names
and types here makes the value cleaning correct and the suggestions sharper.

**Shown:** the full column list as an editable table. **Context updated:** `confirmed_name`.

---

## Stage 4 — Plan  *(decide the work, per column, from context)*

With confirmed names, types, and expected values, plan each column's actions:

- **Reformat** to the column's one format (dates, numbers, phones, emails).
- **Reference-fix** near-miss values to the official list; flag wrong-level or
  unknown ones (don't guess).
- **Repair** encoding damage and Excel date-serials.
- **Coerce** to the expected type where safe; **flag** where not.
- **Flag** out-of-range / impossible values and placeholder codes (`999`, `-1`).
- **Duplicates & outliers** proposed against the confirmed keys / numeric columns.
- **Merge** two values only when context says they mean the same.

Each action becomes a **Decision** with a concrete before→after sample and a
safety label. Safe formatting is queued as auto-but-listed; meaning changes as
pending approval.

**Shown:** a worklist grouped by column, counts of safe vs approval-needed.

---

## Stage 5 — Decide  *(show all, one at a time)*

The person walks the ledger:

- **Safe changes** are shown as a list ("spacing and capitals tidied on 8 columns —
  see what changed"), applied but fully visible.
- **Meaning changes** are shown **severally** — each its own small card with
  before→after, why, and Accept / Reject. Reference fixes, merges, type coercions,
  and outlier/duplicate removals all pass through here.

Rule: **nothing that changes meaning is applied without a sign-off**, and every
decision — accepted or rejected — stays in the log.

**Shown:** the decision cards. **Ledger updated:** `status`.

---

## Stage 6 — Apply & verify  *(do it, then check it held)*

- Apply accepted decisions.
- **Re-validate** each column against its `expected` contract; anything still off is
  raised as a residual flag rather than hidden.
- Confirm IDs kept leading zeros, dates are uniform, references resolved, no new
  breakage introduced.

**Shown:** a short "what changed" confirmation with residual flags, if any.

---

## Stage 7 — Insight  *(the reveal — before & after)*

For numeric columns, show the **distribution before and after**: histogram, mean,
median, outliers, and how much was recovered ("we read 127 values, set aside 10%
we couldn't parse, flagged 3 outliers"). This is offered wherever data appears —
on upload as a first look, and after cleaning as the pay-off — not only in the
toolkit.

**Shown:** interactive before/after charts.

---

## Stage 8 — Export  *(clean file + full trail)*

- Export the cleaned data — **multi-sheet workbooks keep every sheet and its name**.
- Export the **change log**: every decision, before→after, who signed off, when.
- Optionally re-usable: save the confirmed structure + types as a **template** so
  the next file of the same shape skips straight to review.

**Shown:** download links and a one-line summary.

---

## How the hard cases fall out of this pipeline

| Case you hit | Where the pipeline handles it |
| --- | --- |
| Banner/title rows read as header | Stage 1.2 finds the data region first |
| Multi-row / merged headers | Stage 1.1 + 1.4 (un-merge, compose one name) |
| Headers appearing in rows | Stage 1.5 orientation (transpose / form detection) |
| Wrong sheet ("check") chosen; sheets merged | Stage 1.7 + Stage 0 (per-sheet, keep all) |
| Footnote codes (`y,v`) turned to True/False | Stage 2 whole-column typing + boolean guard |
| IDs losing leading zeros | Stage 2 code/ID vs number, expected format |
| "It cleaned but the result is nonsense" | Stages 1–3 fix structure before any value work |
| Decisions not visible in review | Stages 4–5 — every decision is a shown card |
| Big files crash | Stage 0 chunked/streaming read + size guard |

---

## What exists today vs. what this spec adds

**Already in the engine (tested):** per-sheet reading, un-merge, banner-skipping and
multi-row header composition, whole-column typing with the boolean guard, reference
matching, distribution before/after, per-tool flows, privacy AI switch.

**This spec adds / formalises:** the single **Context** object and **Decisions ledger**
threaded through all stages; **orientation detection** (transpose / form); **header
review as an explicit first UI step**; **every decision surfaced** in review and log;
**re-validation** after apply; **chunked/streaming** big-file handling and **cancel**;
and the insight reveal offered **everywhere**, not only in the toolkit.

Recommended build order: (1) header-review-first + Context/ledger, (2) orientation
detection, (3) decision-surfacing in review, (4) big-file streaming + cancel,
(5) insight-everywhere.

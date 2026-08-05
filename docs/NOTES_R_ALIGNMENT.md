# Aligning the engine to the NCC MASTER R script

This records what was ported from the R cleaning script, where the Python
reproduces the R behaviour exactly (quirks included), and the few genuine
decisions that are yours to make rather than mine to guess.

## What this script actually is

The MASTER script cleans **NCC telecoms complaints** (June 2025 – March 2026),
not a citizen register. Its columns are complaint-shaped: `State`, `LGA`,
`created_date_time` / `closed_date`, `Service Provider`, `Category`,
`Ticket_source`, `Closed- within SLA`. There is **no NIN validation and no
phone-number normalisation** in it — those belong to the social-register use
case (SOCU) from the earlier mockup, not here. So the `nin` and `phone_ng`
transforms remain for that use case; the NCC plan does not use them.

## Faithfully ported (with alignment tests in `tests/test_r_alignment.py`)

| R logic | Python transform | Notes |
|---------|------------------|-------|
| `create_state_mapping()` + state cleaning | `state_ng` + `reference/ng_states.json` | Full 37-state map, verbatim variations |
| 5-step LGA pipeline | `lga_ncc` | basic → special chars → suffix strip → concatenation fixes → compound standardise; UPPERCASE output, `UNKNOWN` sentinel |
| `parse_ymd_fallback_dt` cascade + range nulling | `date_iso` | many formats → ISO; out-of-window years nulled + flagged |
| Provider gsub block + MNO/ISP lists | `provider`, `provider_type` | anchored exact-match normalise; type = MNO/ISP |
| Category `case_when` | `category` | ordered keyword rules on upper-cased text |
| Ticket source `str_detect` chain | `ticket_source` | 7 buckets |
| SLA Yes/No logic | `sla` | Yes / No / blank |

Run: `python tests/test_r_alignment.py`.

## Quirks reproduced bug-for-bug — please confirm these are what you want

1. **Parentheses are stripped BEFORE the state lookup.** The cleaning does
   `remove "(...)"` first, so the text *outside* the parentheses decides the
   match. Consequences in your current data:
   - `Onitsha(Abia)` → **ANAMBRA** (Onitsha's usual state), not ABIA
   - `Ibadan(Osun)` → **OYO**, not OSUN
   - `Benin(Ondo)` → **EDO**, not ONDO

   Because of this, the explicit parenthetical aliases you listed in the map
   (e.g. `"Onitsha(Abia)" → ABIA`) are **never reached** — the paren-strip runs
   first. If the intent was the opposite (the value *inside* the parentheses is
   the true state), the algorithm should be inverted. This is a one-line change,
   but it's a judgement call about what those records mean, so I've left the R
   behaviour in place and flagged it here.

2. **Unrecognised values are DROPPED in R, FLAGGED here.** R does
   `filter(!is.na(State))` (and the same for unknown providers), deleting those
   rows. Yet the script's own Word note says *"Records are NEVER deleted due to
   missing dates or fields."* The code and the note disagree. This engine
   follows the **note**: it flags and keeps by default. To match R's exact row
   counts instead, set `on_unrecognized: "null"` on the state mapping and add a
   drop step. Recommendation: keep + flag (an unmatchable state is a data-quality
   signal worth seeing, not a row to silently lose).

3. **Date default is month-first.** NCC files are US-style (`1/1/2026`,
   `3/9/26 8:29`), so `date_iso` defaults to month-first. Day-first sources
   (e.g. the SOCU register) must set `dayfirst: true` in their plan.

## Deliberately not ported (they are pipeline / analysis, not column cleaning)

The engine's job ends at a clean, standardised file. These parts of the script
are downstream orchestration and reporting, and belong in separate layers:

- **Multi-file ingest**: the loader (xlsx / multi-tab / CSV with BOM detection),
  the September-from-File-1 exclusion, and the type-harmonised `bind_rows`. This
  is an ingestion layer that feeds the engine; worth building as `engine/ingest.py`.
- **Derived metrics & features**: `resolution_days` / `resolution_hours`,
  `month` / `day_of_week` / `is_weekend`, and the data-quality flags.
- **Analytics & outputs**: the provider/state scorecards, monthly coverage, the
  intervention pipeline (spike / progressive / SLA methods, priority matrix), the
  ggplot PNGs, and the `officer`/`flextable` Word documents.

None of these change what "clean" means for a column; they consume the clean
output. They can be added as an analysis layer on top of the engine.

## The real equivalence milestone

These alignment tests prove the transforms match the R logic on representative
strings. Full equivalence means running the transforms over the **actual NCC
source files** and diffing the result against
`NCC_Cleaned_COMPREHENSIVE_PowerBI.csv`, column by column. When a de-identified
copy of those files is available, I can build that diff harness so any
divergence shows up as a concrete row/column difference rather than a judgement.

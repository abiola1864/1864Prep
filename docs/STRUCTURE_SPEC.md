# 1864 Prep — Structure detection (wide / panel → long)

## Problem
Some files are **wide panel data**: a few identifier columns (Country, Sex, ID)
followed by many columns whose HEADERS are a sequence — years (1960…2019),
months, or Q1–Q4. Each such header is a *value of a time variable*, not a real
column name. The engine was typing each year as an independent column and even
inventing names for headerless ones. A human sees "these are one time axis + a
measure". The engine must too.

## Goal
Before per-column typing, look at the WHOLE table and detect a wide/panel shape.
If found, tell the user plainly and offer to reshape to **long** format
(the default), with "keep wide" as the opt-out.

## Detector (engine/structure.py :: detect_structure(df))
Signals (all computed from headers + a sample, cheap):
- A run of >= 5 columns whose headers match a sequence:
  - years: 4-digit ints in 1900–2099, mostly consecutive/increasing
  - months: Jan..Dec or 01..12
  - quarters: Q1..Q4 / 2019Q1 etc.
- Those "sequence" columns hold mostly the SAME kind of value (numeric),
  i.e. a measure repeated across the axis.
- There are 1..K non-sequence columns to the LEFT (the id columns).

Return:
{ kind: "panel_wide" | "flat",
  id_cols: [...], value_cols: [...], axis_name: "year"|"month"|"quarter"|"period",
  confidence: 0..1, n_periods: int }

Conservative: only report panel_wide when >= 5 sequence columns AND they are
mostly numeric AND there is >= 1 id column. Otherwise "flat" (unchanged behaviour).

## Reshape (engine/reshape.py :: to_long(df, id_cols, value_cols, axis_name, value_name))
melt: keep id_cols, turn value_cols into two columns [axis_name, value_name].
Drop empty value cells. Return the long dataframe.

## API
- /api/profile already returns headers+columns. Add a `structure` block:
  { kind, id_cols, value_cols, axis_name, n_periods, confidence } computed on upload.
- New POST /api/reshape_long { session_id | file, id_cols, value_cols, axis_name }
  → returns the reshaped preview + new headers/types (re-profiled).

## UX
- On upload, if structure.kind == panel_wide:
  a small popup (not a wall of text):
    "Looks like panel data — <n> <axis>s (e.g. 1960–2019) across the top.
     Reshape to long format? (recommended)"   [Reshape to long]  [Keep wide]
- Default action = Reshape to long. Keep wide = proceed as today.
- After reshape, the columns review shows the tidy long columns
  (id cols + <axis> + value), so the headerless-year mess disappears.

## Out of scope now
- Multi-measure wide blocks (several measures interleaved). Detect only the
  single-measure year/month/quarter panel first.
- Multi-row headers feeding the panel (handled by existing ingest, not here).

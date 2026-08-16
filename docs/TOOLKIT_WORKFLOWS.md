# Toolkit workflows: audit and redesign

## The problem you spotted

Every Data Toolkit item runs the same shape today: **upload → run → download**. In
the code, each tool is a single function `df -> (result, summary)` registered in
`TOOLS` as `(title, description, output_kind)`. There is no step to clean the
columns first, no way to pick which columns a tool acts on, and no sequence that
matches how the task is actually done. That is the flaw: a summary, an outlier
check, and a duplicate check are not the same activity, so they should not share
one generic flow.

## What good tools do (and why)

From how the strongest interactive data tools work (OpenRefine, Trifacta Wrangler)
and standard analysis practice, three principles hold across every task:

1. **Explore before you act.** Look at the data (facets, distributions) before
   changing anything. For outliers specifically, the accepted first step is to
   inspect the distribution (box plot / histogram) and pick a method to match its
   shape: IQR for skewed data, Z-score / MAD for roughly symmetric data.
2. **Preview before you commit, review before you finalise.** Show the change, or
   the flagged rows, and let the person accept or reject. Never mutate silently.
3. **Work on clean, chosen columns.** Resolve column names and types first, then
   let the person choose which columns the tool should act on.

Two more, carried from the wizard: **keep a change log** (every action recorded),
and **nothing that changes meaning happens without approval.**

## The redesign: one flow per tool

Each tool now declares its own ordered steps (`engine/flows.py`, served at
`GET /api/tool/{name}/flow`). The interface renders the steps for the chosen tool.
Step counts differ by tool because the tasks differ:

| Tool | Steps | Sequence |
|---|---|---|
| **Outliers** | 6 | clean → pick numeric columns → **look at the spread** → choose method (IQR vs Z-score) → **review flagged** → decide (keep / cap / remove) → export |
| **Duplicates** | 6 | clean → pick match columns → **check confusing columns** → exact vs near → **review each group** → choose which to keep → export |
| **Validate** | 5 | clean → pick required fields → set rules → review issues → export report |
| **Match & merge** | 6 | add files → clean → confirm shared key → choose join type → preview result → export |
| **Anonymise** | 5 | clean → pick sensitive columns → choose method (hash / mask / drop) → preview before/after → export |
| **Summarise** | 4 | clean → pick columns → choose summary (overview / numbers / categories) → view & export |
| **Remove duplicates, Combine, Compare, Quick clean, Guess gender** | 3 | clean → run → export (these are genuinely one clear action) |

### Outliers: why 6 steps, not 1

Removing outliers blindly biases the data. Best practice is: **see the shape**,
choose a method that fits it, **look at what got flagged**, judge whether each is a
real value or an error, then decide treatment — keep and document, cap
(winsorise), or remove — and record what changed. The engine now backs the
"see the shape" step with `outlier_evaluate()`, which returns each column's count,
missing, min, quartiles, max, skew, and a suggested method
(`POST /api/tool/outliers/evaluate`).

### Duplicates: resolve confusion before finalising

Duplicate matching quietly fails when the match columns are themselves messy:
"Ada " vs "ada" look different to an exact match and identical to a loose one. So
before finalising, the flow runs `dedupe_confusion()`
(`POST /api/tool/duplicates/confusion`), which warns about columns with case /
spacing variants or multiple values in one cell, with an example and advice, so
the person tidies first. Then they choose exact vs near, review each group, and
pick which record to keep.

## What was built now

- `engine/flows.py` — declarative per-tool step specs + `get_flow(tool)`.
- `engine/toolkit.py` — `outlier_evaluate()` and `dedupe_confusion()` helpers.
- `app/server.py` — `GET /api/tool/{name}/flow`, `POST /api/tool/outliers/evaluate`,
  `POST /api/tool/duplicates/confusion`.
- Tests in `tests/test_flows.py` (all suites pass).

## What remains (interface wiring)

The engine and API now express the right flows; the interface still renders a
single run screen. Next: have the toolkit read `…/flow` and render each step,
add the shared **clean-columns-first** and **pick-columns** screens (reused across
tools), and wire the outlier evaluate and duplicate confusion screens to their
endpoints.

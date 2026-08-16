"""Per-tool workflows.

The old toolkit treated every tool the same: upload, run, download. But people
do not analyse the same way for every task. An outlier check needs you to LOOK
at the spread before deciding; a duplicate check needs you to resolve confusing
columns before it finalises; a summary needs you to pick which columns matter.

This module declares, for each tool, the real sequence a non-technical person
would follow. Two principles run through all of them, taken from how the best
interactive tools (OpenRefine, Trifacta) work:

  1. Clean and choose columns FIRST, so the tool acts on data that means what
     the person thinks it means.
  2. Preview before committing, and review before finalising.

Steps are declarative so the interface can render the right screens per tool.
`kind` tells the UI what kind of screen to show; the engine provides the data
each step needs.
"""
from __future__ import annotations

# step kinds the interface knows how to render:
#   clean          - resolve headers/types first (reuses the wizard's cleaning)
#   select_columns - pick columns (optionally filtered, e.g. numeric only)
#   evaluate       - show a read-out (distribution, counts) so the person can judge
#   choose         - pick one option (method, strictness, keep-rule, treatment)
#   review         - inspect flagged rows/groups and accept or reject
#   warn           - surface problems to resolve before continuing
#   run            - do the work
#   export         - download the result and the change log

_CLEAN = {"id": "clean", "label": "Clean columns first",
          "kind": "clean",
          "why": "Fix column names and types before anything else, so the tool works on data that means what you think it means."}


def _pick(filter_=None, why=""):
    return {"id": "pick", "label": "Pick columns", "kind": "select_columns",
            "filter": filter_, "why": why}


FLOWS: dict[str, list[dict]] = {
    # ── Outliers: inspect the spread, then decide per column (≈6 steps) ──
    "outliers": [
        _CLEAN,
        _pick("numeric", "Choose which numeric columns to check. Only numbers have outliers."),
        {"id": "evaluate", "label": "Look at the spread", "kind": "evaluate",
         "why": "See each column's shape (min, median, max, skew) before flagging anything."},
        {"id": "method", "label": "Choose how strict", "kind": "choose",
         "options": ["IQR — best for skewed data", "Z-score — best for bell-shaped data"],
         "why": "Skewed data (most real data) suits the IQR rule; evenly spread data suits Z-score."},
        {"id": "review", "label": "Review what was flagged", "kind": "review",
         "why": "Look at each flagged value. Is it a genuine error, or a real extreme worth keeping?"},
        {"id": "decide", "label": "Decide what to do", "kind": "choose",
         "options": ["Keep and just note them", "Cap to the limit (winsorise)", "Remove the rows"],
         "why": "Remove or cap clear errors; keep real extremes. Whatever you choose is logged."},
        {"id": "export", "label": "Export", "kind": "export"},
    ],

    # ── Duplicates: pick keys, resolve confusion, then finalise (≈6 steps) ──
    "duplicates": [
        _CLEAN,
        _pick(None, "Choose the columns that decide whether two rows are the same person or record."),
        {"id": "confusion", "label": "Check confusing columns", "kind": "warn",
         "why": "Before matching, flag columns whose values are inconsistent (mixed case, spacing, formats) so matches are not missed or over-counted."},
        {"id": "strictness", "label": "Exact or near matches", "kind": "choose",
         "options": ["Exact only", "Near matches too (typos, spacing)"],
         "why": "Near-matching catches 'Ada ' and 'ada', but review them, since it can over-merge."},
        {"id": "review", "label": "Review each group", "kind": "review",
         "why": "Look at each set of possible duplicates and confirm they really are the same."},
        {"id": "keep", "label": "Which one to keep", "kind": "choose",
         "options": ["Keep the first", "Keep the last", "Keep the most complete"],
         "why": "When removing, decide which record in each group to keep."},
        {"id": "export", "label": "Export", "kind": "export"},
    ],

    # ── Summary / profile: clean, pick, choose stats, read (≈4 steps) ──
    "summarise": [
        _CLEAN,
        _pick(None, "Choose which columns to summarise, or leave all selected."),
        {"id": "stats", "label": "Choose the summary", "kind": "choose",
         "options": ["Overview (type, filled %, distinct, example)", "Numbers (min, mean, median, max)", "Categories (top values, counts)"],
         "why": "Pick the kind of summary that fits the question you have."},
        {"id": "export", "label": "View and export", "kind": "export"},
    ],

    # ── Validate: clean, pick required fields + rules, review, export ──
    "validate": [
        _CLEAN,
        _pick(None, "Choose the columns that must be present and valid (e.g. ID, phone, email)."),
        {"id": "rules", "label": "Set the rules", "kind": "choose",
         "options": ["Required (not blank)", "Valid email", "Valid phone", "Within a range"],
         "why": "Say what 'valid' means for each chosen column."},
        {"id": "review", "label": "Review the issues", "kind": "review",
         "why": "See the rows that fail, grouped by problem, before you export the report."},
        {"id": "export", "label": "Export issues report", "kind": "export"},
    ],

    # ── Match & merge: needs two+ files, confirm key, preview join ──
    "match": [
        {"id": "files", "label": "Add the files", "kind": "select_files",
         "why": "Match needs two or more files that share a common column."},
        _CLEAN,
        {"id": "key", "label": "Confirm the shared column", "kind": "choose",
         "why": "The tool guesses the shared ID; confirm or change it before joining."},
        {"id": "how", "label": "How to join", "kind": "choose",
         "options": ["Keep all rows (outer)", "Only matches (inner)", "Keep left file's rows"],
         "why": "Decide what happens to rows that exist in one file but not the other."},
        {"id": "review", "label": "Preview the result", "kind": "review",
         "why": "Check how many rows matched, and how many did not, before exporting."},
        {"id": "export", "label": "Export", "kind": "export"},
    ],

    # ── Anonymise: clean, pick sensitive columns, choose method, export ──
    "anonymise": [
        _CLEAN,
        _pick(None, "Choose the columns to hide (names, IDs, phones, emails)."),
        {"id": "method", "label": "How to hide them", "kind": "choose",
         "options": ["Hash (one-way, consistent)", "Mask (keep the shape)", "Drop the column"],
         "why": "Hashing keeps records linkable without revealing the value; masking keeps only the pattern."},
        {"id": "review", "label": "Preview", "kind": "review",
         "why": "See a before/after sample so you are sure nothing sensitive remains."},
        {"id": "export", "label": "Export", "kind": "export"},
    ],

    # ── Remove duplicates: the action version of the duplicates check ──
    "dedupe": [
        _CLEAN,
        _pick(None, "Choose the columns that decide two rows are the same. Leave all for whole-row duplicates."),
        {"id": "confusion", "label": "Check confusing columns", "kind": "warn",
         "why": "Warn about inconsistent values in the match columns before removing anything."},
        {"id": "keep", "label": "Which one to keep", "kind": "choose",
         "options": ["Keep the first", "Keep the last", "Keep the most complete"],
         "why": "Decide which record to keep from each duplicate group."},
        {"id": "review", "label": "Preview what will go", "kind": "review",
         "why": "See the rows that would be removed before committing."},
        {"id": "export", "label": "Export cleaned file", "kind": "export"},
    ],

    # ── Compare two files: what changed between old and new ──
    "compare": [
        {"id": "files", "label": "Add old and new", "kind": "select_files",
         "why": "Compare needs two versions of the same data: an older file and a newer one."},
        _CLEAN,
        {"id": "key", "label": "Confirm the row key", "kind": "choose",
         "why": "The tool guesses the column that identifies a row; confirm it so changes line up."},
        {"id": "focus", "label": "What to show", "kind": "choose",
         "options": ["Everything", "Only added", "Only removed", "Only changed"],
         "why": "Focus the report on the change you care about."},
        {"id": "review", "label": "Review the differences", "kind": "review",
         "why": "See added, removed and changed rows before exporting."},
        {"id": "export", "label": "Export change report", "kind": "export"},
    ],

    # ── Combine / append: stack files that share columns ──
    "combine": [
        {"id": "files", "label": "Add the files", "kind": "select_files",
         "why": "Combine stacks several files with the same columns into one."},
        {"id": "align", "label": "Check the columns line up", "kind": "warn",
         "why": "Warn if the files' columns do not match, so rows are not misaligned."},
        {"id": "review", "label": "Preview the stack", "kind": "review",
         "why": "See the combined row count and a sample before exporting."},
        {"id": "export", "label": "Export combined file", "kind": "export"},
    ],

    # ── Estimate gender: opt-in, from a name column, never overwrites ──
    "guess_gender": [
        _CLEAN,
        {"id": "pick", "label": "Pick the name column", "kind": "select_columns",
         "filter": "name", "why": "Choose the column that holds people's names."},
        {"id": "consent", "label": "Confirm this is okay", "kind": "choose",
         "options": ["Add a new gender-estimate column", "Cancel"],
         "why": "Gender is only ever estimated into a NEW column, never over your data, and unisex names are left blank."},
        {"id": "review", "label": "Preview estimates", "kind": "review",
         "why": "Check a sample of names and their estimates before exporting."},
        {"id": "export", "label": "Export", "kind": "export"},
    ],
}

# tools that are genuinely one clear action keep the simple flow
_SIMPLE = {
    "quick_clean": "Clean every column automatically and download.",
}


def get_flow(tool: str) -> list[dict]:
    """The ordered steps for a tool. Tools without a tailored flow fall back to
    the simple clean → run → export sequence."""
    if tool in FLOWS:
        return FLOWS[tool]
    return [
        _CLEAN,
        {"id": "run", "label": "Run", "kind": "run",
         "why": _SIMPLE.get(tool, "Run the tool on your file.")},
        {"id": "export", "label": "Export", "kind": "export"},
    ]


def flow_summary() -> dict[str, int]:
    """How many steps each tool has (for tests and docs)."""
    from .toolkit import TOOLS
    return {t: len(get_flow(t)) for t in TOOLS}

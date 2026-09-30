"""Classify what a sheet actually IS before trying to tabularise it.

Real government files are often not rectangular data tables: they're fill-in forms
(Name: ____, Date: ____), checklists (a single column of items), or documents with
a small table embedded in the middle. Forcing those into columns/rows produces
nonsense. This module looks at the raw grid and decides:

  - "table"   : a normal rectangular data table (proceed as usual)
  - "form"    : label:value pairs / sparse grid (extract field->value instead)
  - "list"    : a single meaningful column (treat as a list)
  - "embedded": a form/sparse sheet that contains a detectable table block

and, for form/embedded, returns what to extract.
"""
from __future__ import annotations

import re


def _grid(rows):
    return [[("" if c is None else str(c)).strip() for c in r] for r in rows]


def _density(grid):
    cells = sum(len(r) for r in grid) or 1
    filled = sum(1 for r in grid for c in r if c)
    return filled / cells


def _looks_label(s):
    # "Name:", "Departure Date :", "Total Cost" used as a prompt
    return bool(re.search(r":\s*$", s)) or bool(re.fullmatch(r"[A-Za-z][A-Za-z /()\-]{1,40}", s))


def _find_table_block(grid, min_cols=3, min_rows=3):
    """Find the largest contiguous block of rows that share a wide, filled header
    (a real table embedded in a sparse sheet). Returns (start, end, ncols) or None."""
    best = None
    n = len(grid)
    for i, row in enumerate(grid):
        width = sum(1 for c in row if c)
        if width < min_cols:
            continue
        # candidate header row: count how many following rows have >=2 filled cells
        j = i + 1
        body = 0
        while j < n and sum(1 for c in grid[j] if c) >= 2:
            body += 1; j += 1
        if body >= min_rows - 1:
            span = j - i
            if best is None or span > (best[1] - best[0]):
                best = (i, j, width)
    return best


def classify_sheet(rows) -> dict:
    grid = _grid(rows)
    grid = [r for r in grid if any(c for c in r)]  # drop fully-blank rows for the shape read
    if not grid:
        return {"kind": "empty"}
    ncols = max((len(r) for r in grid), default=0)
    dens = _density(grid)
    # column fill profile
    col_fill = [0] * ncols
    for r in grid:
        for k, c in enumerate(r):
            if c:
                col_fill[k] += 1
    filled_cols = sum(1 for f in col_fill if f >= max(2, 0.3 * len(grid)))

    # LIST: essentially one meaningful column
    if filled_cols <= 1 and ncols <= 4:
        return {"kind": "list"}

    # TABLE: reasonably dense and multiple well-filled columns
    if dens >= 0.5 and filled_cols >= 2:
        return {"kind": "table"}

    # sparse sheet -> form, possibly with an embedded table
    block = _find_table_block(grid)
    label_cells = sum(1 for r in grid for c in r if _looks_label(c))
    if block and (block[1] - block[0]) >= 3:
        return {"kind": "embedded", "table": {"start": block[0], "end": block[1], "ncols": block[2]},
                "label_cells": label_cells}
    if label_cells >= 3 or dens < 0.35:
        return {"kind": "form", "label_cells": label_cells}
    return {"kind": "table"}   # default: let the normal path try


def extract_form_pairs(rows) -> list[dict]:
    """Turn a form into tidy field->value rows. A label is a cell ending in ':' (or a
    short prompt); its value is the next non-empty cell to the right, else the cell
    directly below."""
    grid = _grid(rows)
    out = []
    n = len(grid)
    for i, row in enumerate(grid):
        for k, c in enumerate(row):
            if not c:
                continue
            lab = c.rstrip()
            if lab.endswith(":") or (re.fullmatch(r"[A-Za-z][A-Za-z /()\-]{1,40}", lab) and lab.lower() not in ("date",)):
                field = lab.rstrip(":").strip()
                # value: next non-empty to the right
                val = ""
                for c2 in row[k + 1:]:
                    if c2:
                        val = c2; break
                if not val and i + 1 < n:  # else the cell below
                    below = grid[i + 1]
                    if k < len(below) and below[k]:
                        val = below[k]
                if field:
                    out.append({"field": field, "value": val})
    return out

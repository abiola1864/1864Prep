"""Privacy-preserving AI assist.

The base tool is fully offline. AI assistance is an OPTIONAL enhancement that
only runs when the user turns it on, which requires going online. When it runs,
it must never send the dataset. This module builds the smallest possible request
for ONE column at a time:

  * a few DISTINCT sample values (not rows, so nothing can be recombined into a
    person's record),
  * decoupled from every other column,
  * optionally masked (digits/letters replaced) or reduced to value shapes, so
    the exact values are never revealed while the pattern the model needs is
    kept.

Nothing here calls a network. It prepares a safe payload and records exactly
what would be sent, so the interface can show the user before anything leaves
the machine.
"""
from __future__ import annotations

import hashlib
import re

MODES = ("samples", "masked", "shapes", "labels_only")
_SENSITIVE_HINT = re.compile(
    r"\b(name|surname|first[_ ]?name|last[_ ]?name|phone|msisdn|email|nin|bvn|"
    r"passport|account|acct|address|dob|birth|patient|client|id)\b", re.I)


def looks_sensitive(column_name: str) -> bool:
    # normalise separators so snake_case / kebab-case names are caught
    norm = re.sub(r"[_\-.]+", " ", str(column_name or ""))
    return bool(_SENSITIVE_HINT.search(norm))


def default_mode(column_name: str) -> str:
    """Sensitive columns default to masked shapes; others to plain samples."""
    return "masked" if looks_sensitive(column_name) else "samples"


def _mask(value: str) -> str:
    """Replace the content but keep the shape: 080-31 -> 999-99, Ada -> Xxx."""
    out = []
    for ch in str(value):
        if ch.isdigit():
            out.append("9")
        elif ch.isupper():
            out.append("X")
        elif ch.islower():
            out.append("x")
        else:
            out.append(ch)
    return "".join(out)


def _shape(value: str) -> str:
    """Coarser than mask: just the pattern class. 08031234567 -> [11 digits]."""
    s = str(value).strip()
    if s == "":
        return "[empty]"
    if re.fullmatch(r"\d+", s):
        return f"[{len(s)} digits]"
    if re.fullmatch(r"[A-Za-z]+", s):
        return f"[{len(s)} letters]"
    if re.fullmatch(r"[\d.,]+", s):
        return "[number]"
    return "[mixed]"


def sample_distinct(values, k: int = 12) -> list[str]:
    """Up to k distinct, non-empty values, first-seen order (deterministic)."""
    seen, out = set(), []
    for v in values:
        s = "" if v is None else str(v).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
            if len(out) >= k:
                break
    return out


def build_column_query(column_name: str, values, task: str = "type",
                       mode: str | None = None, k: int = 12) -> dict:
    """Build the minimal, privacy-preserving request for ONE column.

    Returns a dict describing exactly what would be sent. `preview` is the
    human-readable text the interface shows the user before anything leaves.
    """
    mode = mode or default_mode(column_name)
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    raw = sample_distinct(values, k)
    if mode == "samples":
        shown = raw
    elif mode == "masked":
        shown = [_mask(v) for v in raw]
    elif mode == "shapes":
        shown = sorted({_shape(v) for v in raw})
    else:  # labels_only
        shown = []

    prompts = {
        "type": "What kind of data is this column (date, number, phone, email, name, id, category, or free text)?",
        "canonical": "These are category labels from one column. Group the ones that mean the same thing and give a single clean label for each group.",
        "clean_name": "Suggest a short, clear, human-readable column name for a field holding values like these.",
    }
    question = prompts.get(task, prompts["type"])

    return {
        "column": str(column_name),
        "task": task,
        "mode": mode,
        "question": question,
        "sent_values": shown,                     # exactly what leaves, nothing more
        "distinct_sampled": len(raw),
        "row_count_hidden": True,                  # never send counts that re-identify
        "note": ("Sensitive column: values are masked to their shape."
                 if mode in ("masked", "shapes") else
                 "Only a few distinct sample values are sent, never full rows."),
        "preview": _preview(column_name, question, shown, mode),
    }


def _preview(col: str, question: str, shown: list[str], mode: str) -> str:
    body = ", ".join(shown[:12]) if shown else "(no values, column name and type only)"
    return (f"Column: {col}\nAsking: {question}\n"
            f"Sending ({mode}): {body}")


def is_full_dataset(payload: dict) -> bool:
    """Guard the interface can assert against: a payload must be single-column."""
    return not ({"column", "sent_values"} <= set(payload))

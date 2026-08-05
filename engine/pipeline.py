"""The cleaning pipeline.

Reads a *plan* (JSON) — a list of column mappings, each naming a source column,
a target field, a transform, and its parameters — and executes it over a
DataFrame. It runs entirely locally; nothing leaves the machine. It returns the
standardised table, a structured audit log, and the subset of rows that any
transform flagged for human review.

A plan is exactly what the AI mapping layer produces. This module is the
deterministic executor the brief promises: the model proposes, this runs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .transforms import get_transform


@dataclass
class CleaningReport:
    plan_name: str
    source_file: str
    started_at: str
    n_rows_in: int
    columns: list[dict] = field(default_factory=list)
    n_rows_flagged: int = 0

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(
            {
                "plan": self.plan_name,
                "source_file": self.source_file,
                "run_at": self.started_at,
                "rows_in": self.n_rows_in,
                "rows_with_a_flag": self.n_rows_flagged,
                "columns": self.columns,
            },
            indent=indent,
            ensure_ascii=False,
        )


def load_plan(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_table(path: str | Path) -> pd.DataFrame:
    """Read a local file. Supports the formats agencies actually send."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in {".xlsx", ".xls", ".xlsm"}:
        return pd.read_excel(p, dtype=str)
    if suffix == ".csv":
        return pd.read_csv(p, dtype=str, keep_default_na=False)
    if suffix in {".tsv", ".tab"}:
        return pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False)
    raise ValueError(f"Unsupported file type: {suffix}")


def run_plan(df: pd.DataFrame, plan: dict, source_file: str = "") -> tuple[pd.DataFrame, CleaningReport, pd.DataFrame]:
    """Apply a plan. Returns (cleaned_df, report, flagged_rows_df)."""
    report = CleaningReport(
        plan_name=plan.get("name", "unnamed"),
        source_file=source_file,
        started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        n_rows_in=len(df),
    )

    out = pd.DataFrame(index=df.index)
    flagged_mask = pd.Series(False, index=df.index)

    for m in plan["mappings"]:
        src = m["source_column"]
        tgt = m["target_field"]
        tname = m["transform"]
        params = dict(m.get("params", {}))

        if src not in df.columns:
            report.columns.append({
                "source_column": src, "target_field": tgt, "transform": tname,
                "error": "source column not found in file",
            })
            continue

        tf = get_transform(tname, **params)
        result = tf.run(df[src], src, tgt)
        out[tgt] = result.series

        for change in result.flags:
            flagged_mask.iloc[change.row] = True

        report.columns.append(result.summary())

    # Carry through any columns the plan didn't touch, so nothing is lost.
    passthrough = [c for c in df.columns if c not in {m["source_column"] for m in plan["mappings"]}]
    for c in passthrough:
        if c not in out.columns:
            out[c] = df[c].values

    flagged_rows = out[flagged_mask.values].copy()
    report.n_rows_flagged = int(flagged_mask.sum())
    return out, report, flagged_rows


def clean_file(input_path: str | Path, plan_path: str | Path) -> dict:
    """Convenience wrapper: read file + plan, run, return everything in memory."""
    df = read_table(input_path)
    plan = load_plan(plan_path)
    cleaned, report, flagged = run_plan(df, plan, source_file=str(input_path))
    return {"cleaned": cleaned, "report": report, "flagged": flagged}

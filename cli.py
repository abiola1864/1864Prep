#!/usr/bin/env python3
"""1864 Prep — command-line runner.

Usage:
    python cli.py clean <file> --plan <plan.json> [--out <dir>]
    python cli.py transforms          # list available transforms

Everything runs locally. The input file is read from disk and never sent
anywhere. Three artefacts are written: the standardised table, the audit log
(JSON), and the rows flagged for human review.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engine import clean_file, list_transforms


def cmd_clean(args) -> int:
    in_path = Path(args.file)
    if not in_path.exists():
        print(f"error: file not found: {in_path}", file=sys.stderr)
        return 2

    result = clean_file(in_path, args.plan)
    cleaned = result["cleaned"]
    report = result["report"]
    flagged = result["flagged"]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = in_path.stem

    cleaned_path = out_dir / f"{stem}_STANDARDIZED.csv"
    audit_path = out_dir / f"{stem}_audit.json"
    flagged_path = out_dir / f"{stem}_flagged.csv"

    cleaned.to_csv(cleaned_path, index=False)
    audit_path.write_text(report.to_json(), encoding="utf-8")
    flagged.to_csv(flagged_path, index=False)

    print(f"Plan            : {report.plan_name}")
    print(f"Rows in         : {report.n_rows_in}")
    print(f"Rows with a flag: {report.n_rows_flagged}")
    print(f"Columns mapped  : {len([c for c in report.columns if 'error' not in c])}")
    print()
    print("Wrote:")
    print(f"  cleaned : {cleaned_path}")
    print(f"  audit   : {audit_path}")
    print(f"  flagged : {flagged_path}")
    return 0


def cmd_transforms(_args) -> int:
    print("Available transforms:")
    for t in list_transforms():
        print(f"  - {t}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="1864-prep", description="Local data standardisation for the Open Network on Digital ID.")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("clean", help="clean a file with a plan")
    c.add_argument("file")
    c.add_argument("--plan", required=True)
    c.add_argument("--out", default="out")
    c.set_defaults(func=cmd_clean)

    t = sub.add_parser("transforms", help="list available transforms")
    t.set_defaults(func=cmd_transforms)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

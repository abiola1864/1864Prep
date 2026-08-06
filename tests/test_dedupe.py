"""Tests for near-duplicate rows and similar-value grouping."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.dedupe import group_similar, near_duplicate_rows  # noqa


def test_group_similar_addresses():
    vals = ["Obafemi awolowo road ikeja", "Obafemi awolowo road ikeja Lagos",
            "Obafemi Awolowo road opposite ipodo market",
            "Obafemi awolowo opposite ipodo market", "totally different place"]
    groups = group_similar(vals, threshold=0.8)
    assert groups and groups[0]["size"] >= 2
    biggest = groups[0]["members"]
    assert any("ikeja" in m.lower() for m in biggest) or any("ipodo" in m.lower() for m in biggest)


def test_near_duplicate_rows_exact_and_near():
    df = pd.DataFrame([
        {"name": "MUSA IBRAHIM", "state": "Kano"},
        {"name": "MUSA IBRAHIM", "state": "Kano"},     # exact dup
        {"name": "musa  ibrahim", "state": "kano"},      # near dup (case/space)
        {"name": "Grace Eze", "state": "Enugu"},
    ])
    d = near_duplicate_rows(df)
    assert any(x["kind"] == "exact" and len(x["rows"]) >= 2 for x in d)
    assert any(x["kind"] in ("exact", "near") for x in d)


def test_no_false_groups_on_distinct():
    groups = group_similar(["apple", "orange", "banana", "grape"], threshold=0.85)
    assert groups == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} dedupe tests passed.")

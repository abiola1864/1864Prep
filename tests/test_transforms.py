"""Tests for the transform library and the pipeline.

Run from the repo root:  python -m pytest -q   (or: python tests/test_transforms.py)
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import get_transform, run_plan  # noqa: E402

REF_STATES = "reference/ng_states.json"
REF_LGA = "reference/ng_lga_kaduna.json"


def _one(name, value, **params):
    tf = get_transform(name, **params)
    s = pd.Series([value])
    res = tf.run(s, "src", "tgt")
    val = res.series.iloc[0]
    flagged = res.n_flagged > 0
    return val, flagged


def test_nin():
    assert _one("nin", "12345678901") == ("12345678901", False)
    assert _one("nin", " 123 456 789 01 ") == ("12345678901", False)
    val, flagged = _one("nin", "3456789")
    assert flagged and val == "3456789"


def test_phone_forms_all_normalise():
    for form in ["08031234567", "8031234567", "+2348031234567", "234 803 123 4567", "0803-123-4567"]:
        val, flagged = _one("phone_ng", form)
        assert val == "+2348031234567", form
        assert not flagged, form


def test_phone_bad():
    val, flagged = _one("phone_ng", "12345")
    assert flagged


def test_state_alias_and_ambiguous():
    assert _one("state_ng", "Kastina", reference=REF_STATES) == ("KATSINA", False)
    assert _one("state_ng", "kaduna ", reference=REF_STATES) == ("KADUNA", False)
    assert _one("state_ng", "abuja", reference=REF_STATES) == ("FCT", False)
    # Faithful to R: parentheticals are stripped BEFORE lookup, so this resolves.
    assert _one("state_ng", "Kaduna(Kastina)", reference=REF_STATES) == ("KADUNA", False)
    val, flagged = _one("state_ng", "Atlantis", reference=REF_STATES)
    assert flagged  # genuinely unknown -> flagged


def test_lga_deconcatenation():
    assert _one("lga_ng", "sabongari", reference=REF_LGA) == ("Sabon Gari", False)
    val, flagged = _one("lga_ng", "ZariaTudunWada", reference=REF_LGA)
    assert val == "Zaria" and flagged  # peeled a known LGA, flagged the leftover


def test_dates_various():
    # Register sources are day-first; set dayfirst=True (default is month-first for NCC).
    assert _one("date_iso", "3/9/1990", dayfirst=True) == ("1990-09-03", False)
    assert _one("date_iso", "1998-04-12") == ("1998-04-12", False)   # ISO, unambiguous
    val, flagged = _one("date_iso", "not a date")
    assert flagged


def test_names_and_gender():
    assert _one("name", "OYEBANJO") == ("Oyebanjo", False)
    assert _one("name", "  abiola   t. ") == ("Abiola T.", False)
    assert _one("gender", "FEMALE") == ("F", False)
    val, flagged = _one("gender", "unknown")
    assert flagged


def test_pipeline_end_to_end():
    df = pd.DataFrame({
        "NIN Number": ["3456789", "12345678901"],      # row 0 bad NIN
        "Ph No": ["08031234567", "234 806 000 0000"],
        "Other Names": ["ABIOLA", "fatima"],
        "Surname": ["oyebanjo", "BELLO"],
        "D.O.B": ["3/9/1990", "1998-04-12"],
        "Sex": ["M", "female"],
        "State of Origin": ["Kastina", "Atlantis"],  # row 1 unknown state -> flag
        "LGA": ["sabongari", "Zaria"],
        "Household ID": ["HH-1", "HH-2"],
    })
    plan = {
        "name": "t",
        "mappings": [
            {"source_column": "NIN Number", "target_field": "NIN", "transform": "nin"},
            {"source_column": "Ph No", "target_field": "MSISDN", "transform": "phone_ng"},
            {"source_column": "Other Names", "target_field": "First Name", "transform": "name"},
            {"source_column": "Surname", "target_field": "Last Name", "transform": "name"},
            {"source_column": "D.O.B", "target_field": "Date of Birth", "transform": "date_iso"},
            {"source_column": "Sex", "target_field": "Gender", "transform": "gender"},
            {"source_column": "State of Origin", "target_field": "State", "transform": "state_ng", "params": {"reference": REF_STATES}},
            {"source_column": "LGA", "target_field": "LGA", "transform": "lga_ng", "params": {"reference": REF_LGA}},
        ],
    }
    cleaned, report, flagged = run_plan(df, plan, source_file="unit-test")
    assert list(cleaned["NIN"]) == ["3456789", "12345678901"]
    assert cleaned["MSISDN"].iloc[0] == "+2348031234567"
    assert cleaned["First Name"].iloc[0] == "Abiola"
    assert cleaned["State"].iloc[0] == "KATSINA"
    assert "Household ID" in cleaned.columns          # passthrough preserved
    assert report.n_rows_flagged == 2                 # row 0 (bad NIN) + row 1 (ambiguous state)
    print("end-to-end OK — flagged rows:", report.n_rows_flagged)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} tests passed.")

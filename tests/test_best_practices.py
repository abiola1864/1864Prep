"""Regression tests for common data-cleaning best practices."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import get_transform            # noqa
from engine.profile import profile_column   # noqa


def test_unicode_whitespace_and_zero_width():
    n = get_transform("text_normalise")
    assert n.apply_value("Musa\xa0Ibrahim")[0] == "Musa Ibrahim"   # non-breaking space
    assert n.apply_value("  Kano\u200b ")[0] == "Kano"            # zero-width
    assert n.apply_value("A\tB")[0] == "A B"                      # tab


def test_mojibake_repair():
    assert get_transform("text_normalise").apply_value("Ã©cole")[0] == "école"


def test_leading_zero_codes_stay_identifier():
    assert profile_column(pd.Series(["007","012","034","099","101"]*4), "emp_id").semantic_type == "identifier"
    assert profile_column(pd.Series(["01234","05678","09999"]*4), "zip").semantic_type == "identifier"
    # fixed_id must preserve the zeros
    assert get_transform("fixed_id", length=3).apply_value("007")[0] == "007"
    # genuine measures (no leading zeros) stay numeric
    assert profile_column(pd.Series(["1200","3500","900","4250"]*4), "amount").semantic_type == "numeric"


def test_numbers_with_nbsp_and_currency():
    x = get_transform("numeric")
    assert x.apply_value("1\xa0200,50")[0] == "1200.5"
    assert x.apply_value("₦2,500.00")[0] == "2500"
    assert x.apply_value("(200)")[0] == "-200"
    assert x.apply_value("45%")[0] == "45"


def test_boolean_and_percent_variants():
    b = get_transform("boolean")
    for v in ["Y","yes","TRUE","1"]:
        assert b.apply_value(v)[0] in ("Yes",)
    for v in ["N","no","FALSE","0"]:
        assert b.apply_value(v)[0] in ("No",)



def test_impossible_dates_flagged_not_corrected():
    d = get_transform("date_iso")
    v, flagged, _ = d.apply_value("2021-13-01")     # month 13
    assert flagged and v == "2021-13-01"            # kept as-is, not swapped
    assert d.apply_value("2021-05-32")[1] is True   # day 32
    assert d.apply_value("2021-05-03")[0] == "2021-05-03"  # valid unchanged
    dt = get_transform("datetime_iso")
    assert dt.apply_value("2021-13-01 10:00:00")[1] is True


def test_hyphenated_and_particle_names():
    n = get_transform("name")
    assert n.apply_value("MARY-JANE")[0] == "Mary-Jane"
    assert n.apply_value("o'brien")[0] == "O'Brien"
    assert n.apply_value("MUSA IBRAHIM")[0] == "Musa Ibrahim"


if __name__ == "__main__":
    fns=[v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns: fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} best-practice tests passed.")

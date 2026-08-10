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



def test_column_level_date_order_inference():
    from engine.profile import infer_date_order
    assert infer_date_order(["12.28.2020","06.30.2020","11.22.2019","03.14.2021"]*4)[0] == "MDY"
    assert infer_date_order(["28.12.2020","30.06.2020","22.11.2019","14.03.2021"]*4)[0] == "DMY"
    assert infer_date_order(["2020-12-28","2021-01-15"]*4)[0] == "YMD"
    # all components <=12 -> ambiguous (ask the user), not a wrong guess
    assert infer_date_order(["05.03.2021","01.02.2020"]*4)[0] is None
    # one stray typo must not flip a clearly day-first column
    assert infer_date_order(["28.12.2020","30.06.2020","22.11.2019"]*10 + ["13.28.2020"])[0] == "DMY"



def test_column_level_decimal_convention():
    from engine.profile import infer_decimal_convention
    assert infer_decimal_convention(["42.959","43.245","12.5","900"]*4)[0] == "dot"
    assert infer_decimal_convention(["1.234,56","2.500,00","12,5","7,80"]*4)[0] == "comma"
    # dot-decimal value must survive under dot convention
    x = get_transform("numeric", decimal="dot")
    assert x.apply_value("42.959")[0] == "42.959"
    # European value under comma convention
    y = get_transform("numeric", decimal="comma")
    assert y.apply_value("1.234,56")[0] == "1234.56"
    assert y.apply_value("12,5")[0] == "12.5"



def test_different_numbers_never_merge():
    from engine.induce import _canonical_key
    from engine.dedupe import cluster_similar
    assert _canonical_key("-1") != _canonical_key("1")     # sentinel vs value
    assert _canonical_key("7.0") == _canonical_key("7")    # same number
    for g in cluster_similar(["-1", "1", "1", "-1"] * 3):
        vals = set(g["members"])
        assert not ({"-1", "1"} <= vals), "different numbers must not group"


def test_bom_stripped_from_headers():
    from engine.ingest import _dedupe_headers
    assert _dedupe_headers(["\ufeffrecord_id", " name "]) == ["record_id", "name"]



def test_account_and_age_typing():
    import pandas as pd
    from engine.profile import profile_column
    acct = ["1234567890","0001234567","ABC123","1234567890","ABC123","0001234567"]*4
    assert profile_column(pd.Series(acct), "bank_account").semantic_type == "identifier"  # not phone
    age = ["121","forty","-4","7","0","42","33","19","55","8","67","forty"]*3
    assert profile_column(pd.Series(age), "age_years").semantic_type == "numeric"           # not categorical



def test_excel_serial_headers_and_fractional_serials():
    from engine.ingest import _fix_serial_header
    from engine import get_transform
    assert _fix_serial_header("44562") == "2022-01-01"
    assert _fix_serial_header("ABC") == "ABC" and _fix_serial_header("12345") == "12345"
    assert get_transform("date_iso").apply_value("44562.5")[0] == "2022-01-01"


def test_serial_column_only_dates_with_hint():
    import pandas as pd
    from engine.profile import profile_column
    s = ["44197", "44562", "44927", "45292", "45658", "44835"]
    assert profile_column(pd.Series(s), "created_date").semantic_type == "date"
    assert profile_column(pd.Series(s), "member_code").semantic_type == "identifier"


def test_export_safety_strips_breaking_chars():
    import pandas as pd
    from engine.exporters import _export_safe
    out = _export_safe(pd.DataFrame({"t": ["a\nb", "c\rd", "e\ufffdf"]}))
    assert list(out["t"]) == ["a b", "cd", "ef"]


if __name__ == "__main__":
    fns=[v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns: fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} best-practice tests passed.")

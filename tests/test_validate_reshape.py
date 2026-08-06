"""New cleaning tasks: sentinel codes, range checks, unit numbers, split/merge."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import get_transform  # noqa
from engine.reshape import (date_part, merge_columns, split_by_delimiter,  # noqa
                            split_name, split_number_text)
from engine.profile import profile_column  # noqa


def _run(tf, vals):
    return list(tf.run(pd.Series(vals), "c", "c").series)


def test_sentinel_na():
    tf = get_transform("sentinel_na")
    out = _run(tf, ["23", "999", "45", "-99", "don't know", "12"])
    assert out[1] == "" and out[3] == "" and out[4] == "" and out[0] == "23"


def test_range_check_flags_out_of_range():
    tf = get_transform("range_check", min=0, max=120)
    res = tf.run(pd.Series(["34", "200", "-5", "60"]), "age", "age")
    reasons = {c.row: c.reason for c in res.flags}
    assert 1 in reasons and 2 in reasons and 3 not in reasons   # 200 and -5 flagged, 60 ok


def test_unit_numeric():
    tf = get_transform("unit_numeric")
    out = _run(tf, ["3200g", "12 kg", "5ha", "banana"])
    assert out[0] == "3200" and out[1] == "12" and out[2] == "5"
    # last one has no number -> flagged, value kept
    res = tf.run(pd.Series(["banana"]), "c", "c")
    assert res.flags


def test_unit_numeric_convert():
    tf = get_transform("unit_numeric", to="kg")
    out = list(tf.run(pd.Series(["3200g"]), "w", "w").series)
    assert out[0] == "3.2"


def test_profiler_detects_units():
    s = pd.Series(["3200g", "1500g", "2kg", "800g", "1200g"] * 3)
    p = profile_column(s, "Weight")
    assert p.transform == "unit_numeric"


def test_split_and_merge():
    s = pd.Series(["Lagos, Nigeria", "Kano, Nigeria"])
    d = split_by_delimiter(s, ",")
    assert list(d.iloc[0]) == ["Lagos", "Nigeria"]
    n = split_name(pd.Series(["ADEYEMI, Tunde", "Musa Bello"]))
    assert n.iloc[0]["c_surname" if False else n.columns[1]] in ("Adeyemi",)
    nt = split_number_text(pd.Series(["Musa 34"]))
    assert nt.iloc[0].tolist() == ["Musa", "34"]
    df = pd.DataFrame({"a": ["x", "y"], "b": ["1", "2"]})
    m = merge_columns(df, ["a", "b"], sep="-")
    assert list(m) == ["x-1", "y-2"]


def test_date_part():
    out = list(date_part(pd.Series(["2019-05-03", "3/9/1990"]), "year"))
    assert out[0] == "2019" and out[1] == "1990"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} validate/reshape tests passed.")

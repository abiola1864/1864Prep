"""The trained type classifier rescues columns the rules mis-read (opt-in)."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.profile import profile_column, profile_dataframe  # noqa
from engine.ml.predict import available, predict_type  # noqa


def test_model_present():
    assert available(), "typeclf.joblib should be trained and shipped"


def test_rescues_numeric_with_junk():
    # Mostly spelled-out numbers + some digits: rules can't call this numeric
    # (under half are pure integers, so the plain-integer rule does not fire),
    # but the ML classifier recognises it as numeric. This keeps the ML-rescue
    # path under test after the rules were strengthened for plain integers.
    age = pd.Series(["34","forty","52","fifty","thirty","45","sixty","27","twenty","41","seventy","33"])
    rules = profile_column(age, "How old are you?", use_ml=False)
    ml = profile_column(age, "How old are you?", use_ml=True)
    assert ml.semantic_type == "numeric"
    assert ml.evidence.get("ml_assist") is not None
    # default (no ML) is unchanged / not numeric
    assert rules.semantic_type != "numeric"


def test_ml_off_by_default_is_stable():
    s = pd.Series(["Lagos","Kano","Lagos","Ibadan","Kano","Lagos"])
    a = profile_column(s, "City", use_ml=False)
    b = profile_column(s, "City")  # default
    assert a.semantic_type == b.semantic_type



def test_indicator_and_datetime_and_duplicates():
    import pandas as pd
    from engine.dedupe import duplicate_columns
    ind = pd.Series(["0", "1", "1", "0", "1", "0"] * 3)
    assert profile_column(ind, "opt/Others", use_ml=True).semantic_type == "indicator"
    ts = pd.Series(["2019-05-03 12:41:15", "2019-05-03 15:28:29", "2019-05-06 09:10:00"] * 4)
    assert profile_column(ts, "start", use_ml=True).semantic_type == "datetime"
    df = pd.DataFrame({"Others (specify)": ["a"], "Others (specify).1": ["b"], "Age": ["5"]})
    groups = duplicate_columns(df)
    assert any(len(g["columns"]) == 2 for g in groups)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} ML tests passed.")

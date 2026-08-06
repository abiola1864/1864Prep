"""Tests for generality: type inference on unseen schemas + vocabulary induction."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import get_transform  # noqa: E402
from engine.induce import induce_vocabulary  # noqa: E402
from engine.profile import profile_column, profile_dataframe, profile_to_plan  # noqa: E402

STATES = ["ABIA","LAGOS","KANO","KADUNA","KATSINA","RIVERS","OYO","BENUE","KWARA","OGUN","FCT"]
GAZ = {"ng_state": STATES}


def col(values):
    return pd.Series(values)


def test_type_inference_basic():
    assert profile_column(col(["a@x.com", "b@y.org", "c@z.net"] * 5), "Email").semantic_type == "email"
    assert profile_column(col(["M", "F", "Male", "female"] * 10), "Sex").semantic_type == "gender"
    assert profile_column(col(["Yes", "No", "yes", "no"] * 10), "Active").semantic_type == "boolean"
    assert profile_column(col(["08031234567", "07065551212", "09051112222"] * 5), "GSM").semantic_type == "phone"
    ids = [str(1000000000 + i) for i in range(60)]  # 10-digit ids
    assert profile_column(col(ids), "ID").semantic_type == "identifier"
    nins = [f"{10000000000 + i * 137:011d}" for i in range(60)]  # distinct 11-digit
    p = profile_column(col(nins), "NIN")
    assert p.semantic_type == "identifier" and p.transform == "nin"


def test_decimals_are_numeric_not_id():
    sizes = [str(round(0.5 + i * 0.13, 2)) for i in range(60)]  # 3.45-style
    assert profile_column(col(sizes), "Farm_Size_Ha").semantic_type == "numeric"


def test_dates_and_geo():
    dates = ["2025-03-14", "3/14/2025", "14/03/2025"] * 20
    assert profile_column(col(dates), "Enrol_Date").semantic_type == "date"
    geo = ["Lagos", "lagos", "Kastina", "Kaduna", "ABUJA"] * 12
    assert profile_column(col(geo), "State", GAZ).semantic_type == "geo"


def test_induction_merges_case_not_typos():
    # SAME word, different case -> one category. Typos are NOT auto-merged
    # (they are handled as suggestions by dedupe.group_similar).
    vals = (["Maize"] * 30 + ["maize"] * 8 + ["MAIZE"] * 3        # case variants -> merge
            + ["Maiz"] * 3                                          # typo -> stays separate
            + ["Rice"] * 20 + ["rice"] * 5
            + ["Sorghum"] * 15)
    v = induce_vocabulary(vals)
    # case variants of Maize collapse to a single label
    assert v.mapping["Maize"] == v.mapping["maize"] == v.mapping["MAIZE"] == "Maize"
    # the typo "Maiz" is a DIFFERENT category (not silently merged)
    assert v.mapping["Maiz"] != v.mapping["Maize"]
    # Rice case variants collapse; distinct real words stay distinct
    assert v.mapping["Rice"] == v.mapping["rice"]
    assert len({v.mapping["Maize"], v.mapping["Rice"], v.mapping["Sorghum"]}) == 3


def test_induction_protects_numbers():
    # different numeric ranges must NEVER merge, even with identical words
    vals = ["6 - 10 years", "6-10 Years", "11 - 15 years", "21 - 25 years"]
    v = induce_vocabulary(vals)
    assert v.mapping["6 - 10 years"] == v.mapping["6-10 Years"]      # same range, cosmetic diff
    assert v.mapping["6 - 10 years"] != v.mapping["21 - 25 years"]   # different range, separate
    assert v.n_canonical == 3   # {6-10, 11-15, 21-25}


def test_induction_word_order_and_ampersand():
    vals = ["Drinks, Water, Wine & Spirits", "drinks, water, wine and spirits",
            "Fabrics, Tailoring", "fabrics, tailoring"]
    v = induce_vocabulary(vals)
    assert v.mapping["Drinks, Water, Wine & Spirits"] == v.mapping["drinks, water, wine and spirits"]
    assert v.n_canonical == 2


def test_auto_categorical_transform():
    # case variants merge; typos remain their own value (surfaced elsewhere as suggestions)
    s = col(["Malaria", "malaria", "MALARIA", "Typhoid", "typhoid"] * 10)
    res = get_transform("auto_categorical").run(s, "Diagnosis", "Diagnosis")
    assert set(res.series) == {"Malaria", "Typhoid"}



def test_auto_plan_on_unseen_schema():
    df = pd.DataFrame({
        "BenID": [f"SCH{100000 + i}" for i in range(40)],
        "Phone": ["0803" + str(1000000 + i) for i in range(40)],
        "State": (["Kastina", "Lagos", "Kano", "Benue"] * 10),
        "Active": (["Yes", "No"] * 20),
    })
    profs = profile_dataframe(df, GAZ)
    plan = profile_to_plan(profs, "auto", {"ng_state": "reference/ng_states_canonical.json"})
    tf = {m["source_column"]: m["transform"] for m in plan["mappings"]}
    assert tf["Phone"] == "phone_ng"
    assert tf["State"] == "resolve"
    assert tf["Active"] == "boolean"
    assert tf["BenID"] == "fixed_id"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} profile/induce tests passed.")

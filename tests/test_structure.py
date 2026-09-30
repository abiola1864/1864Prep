import warnings; warnings.filterwarnings("ignore"); import pandas as pd
from engine.structure import detect_structure
from engine.reshape import to_long
def test_wide_panel_detected_and_reshaped():
    df=pd.DataFrame({"Country":["NG","GH"],"Sex":["M","F"],**{str(y):[y-1900,y-1901] for y in range(1960,1972)}})
    s=detect_structure(df)
    assert s["kind"]=="panel_wide" and s["axis_name"]=="year" and s["n_periods"]==12
    lg=to_long(df,s["id_cols"],s["value_cols"],s["axis_name"])
    assert list(lg.columns)==["Country","Sex","year","value"] and len(lg)==24
    print("panel detected + reshaped:", lg.shape)
def test_flat_table_not_flagged():
    df=pd.DataFrame({"name":["a","b"],"age":[1,2],"city":["x","y"],"email":["a@x","b@y"],"phone":["1","2"],"note":["p","q"]})
    assert detect_structure(df)["kind"]=="flat"
    print("flat table left alone")
test_wide_panel_detected_and_reshaped(); test_flat_table_not_flagged()
print("STRUCTURE TESTS PASSED")

def test_messy_sparse_panel_detected():
    import random
    def cell(): return random.choice(["","","..","1,234","12.3%","45*","987","n/a","56"])
    cols={"Country":["NG","GH","KE","ZA"],"Sex":["M","F","M","F"]}
    for y in range(1960,2000): cols[str(y)]=[cell() for _ in range(4)]
    import pandas as pd
    from engine.structure import detect_structure
    assert detect_structure(pd.DataFrame(cols))["kind"]=="panel_wide"
    print("messy sparse panel detected")
test_messy_sparse_panel_detected()

def test_oecd_flag_column_pairing(tmp_path=None):
    # OECD layout: year header empty, value in the next (blank-header) column
    import tempfile, os
    from engine.ingest import read_any
    from engine.structure import detect_structure
    p=tempfile.mktemp(suffix=".csv")
    # header row: Country,Sex,,1960,,1961  (blank flag col after each year)
    lines=["Country,Sex,,1960,,1961",
           "NG,M,,,3.1,,4.2",
           "GH,F,,,5.0,,5.5"]
    open(p,"w").write("\n".join(lines)+"\n")
    df,_=read_any(p)
    # after pairing, years should hold the values and no blank flag cols remain
    assert "1960" in df.columns and "1961" in df.columns
    assert not any("no_header" in str(c).lower() for c in df.columns)
    print("OECD flag-column pairing works:", list(df.columns))
test_oecd_flag_column_pairing()
print("OECD PAIRING TEST PASSED")

def test_form_detected_not_tabulated():
    from engine.structure import detect_form
    import pandas as pd
    rows=[["","",""],["TRAVEL REQUEST","",""],["Name:","","Date:"],["Purpose:","",""],
          ["Traveller:","",""],["Authorized By:","",""],["Approved By:","",""]]
    f=detect_form(pd.DataFrame(rows))
    assert f["is_form"] and len(f["label_values"])>=4
    # a normal table is not a form
    assert not detect_form(pd.DataFrame({"a":[1,2,3],"b":[4,5,6],"c":[7,8,9]}))["is_form"]
    print("form detection works")
test_form_detected_not_tabulated()
print("FORM TEST PASSED")

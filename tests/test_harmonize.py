import warnings; warnings.filterwarnings("ignore"); import pandas as pd
from engine.profile import profile_dataframe
def test_year_columns_are_consistent():
    cols={str(y):[str(y) for _ in range(20)] for y in range(2010,2020)}
    profs=profile_dataframe(pd.DataFrame(cols),{},{},use_ml=False,use_nlp=False)
    types=set(p.semantic_type for p in profs)
    assert len(types)==1, f"year columns should share one type, got {types}"
    print("year columns harmonised to:", types)
def test_mixed_table_stays_distinct():
    df=pd.DataFrame({"email":["a@x.com","b@y.com","c@z.com"],"name":["Ada","Bola","Uche"]})
    profs=profile_dataframe(df,{},{},use_ml=False,use_nlp=False)
    t={p.column:p.semantic_type for p in profs}
    assert t["email"]=="email", t
    print("mixed table preserved:", t)
test_year_columns_are_consistent(); test_mixed_table_stays_distinct()
print("HARMONIZE TESTS PASSED")

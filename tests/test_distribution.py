import warnings; warnings.filterwarnings("ignore"); import pandas as pd
from engine.distribution import distribution_profile, before_after

# raw: numbers stored as text with junk (%, commas) + some unreadable
raw = pd.DataFrame({
    "rate": ["52","97.7","99.4","-","11.5","99.3","88","90","91","3200"],  # 3200 outlier, '-' unreadable
    "name": ["a","b","c","d","e","f","g","h","i","j"],                     # not numeric -> excluded
})
prof = distribution_profile(raw)
print("cols profiled:", [p["column"] for p in prof])
cols={p["column"]:p for p in prof}
assert cols["rate"]["kind"]=="numeric"                    # numeric column profiled
assert "name" in cols and cols["name"]["kind"]=="categorical"   # non-numeric now included too
r = prof[0]
assert r["unreadable_share"] > 0                         # '-' counted as unreadable
assert r["outliers"] >= 1 and "histogram" in r
print("rate stats: mean", r["mean"], "median", r["median"], "outliers", r["outliers"], "unreadable", r["unreadable_share"])

# before/after: cleaning recovers the '-' as missing and keeps numbers
clean = pd.DataFrame({"rate": [52,97.7,99.4,None,11.5,99.3,88,90,91,3200]})
ba = before_after(raw, clean)
print("headline:", ba["headline"])
assert ba["pairs"] and ba["pairs"][0]["before"] and ba["pairs"][0]["after"]
print("ALL DISTRIBUTION TESTS PASSED")

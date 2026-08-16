import warnings; warnings.filterwarnings("ignore"); import pandas as pd
from engine.flows import get_flow, FLOWS
from engine.toolkit import outlier_evaluate, dedupe_confusion

# each tailored tool has its own distinct sequence (not all the same)
lengths = {t: len(get_flow(t)) for t in ["outliers","duplicates","summarise","validate","match","dedupe"]}
print("step counts:", lengths)
assert lengths["outliers"] >= 6 and lengths["duplicates"] >= 6
assert get_flow("quick_clean")[1]["kind"] == "run"   # quick_clean stays simple
assert lengths["outliers"] != lengths["summarise"]   # flows differ per tool
# every flow starts by cleaning/choosing (except match which needs files first)
assert get_flow("outliers")[0]["kind"] == "clean"
assert get_flow("match")[0]["kind"] == "select_files"

# outlier evaluate: read-out + method suggestion, skew-aware
df = pd.DataFrame({"income":[10,11,12,13,12,11,10,9,10,11,900], "name":["a"]*11})
ev = outlier_evaluate(df)
print("evaluate:", ev)
assert ev and ev[0]["column"]=="income" and "suggested_method" in ev[0]
assert ev[0]["shape"] in ("right-skewed","left-skewed","roughly symmetric")

# dedupe confusion: catches case/space variants and multi-value cells
d2 = pd.DataFrame({"email":["Ada@x.com","ada@x.com ","b@x.com"], "tags":["x,y","z","p,q"]})
w = dedupe_confusion(d2)
print("confusion:", [x["issue"] for x in w])
assert any(x["issue"]=="case or spacing variants" for x in w)
assert any(x["issue"]=="multiple values in one cell" for x in w)
print("ALL FLOW TESTS PASSED")

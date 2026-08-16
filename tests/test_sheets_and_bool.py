import warnings; warnings.filterwarnings("ignore")
import pandas as pd, tempfile
from pathlib import Path
from engine.ingest import read_all_sheets, read_excel
from engine.exporters import to_xlsx_multi
from engine.profile import profile_column

TMP = Path(tempfile.mkdtemp())

# --- per-sheet: two sheets processed separately, names + count kept, not merged
p = TMP / "book.xlsx"
with pd.ExcelWriter(p) as w:
    pd.DataFrame({"id":[1,2],"name":["a","b"]}).to_excel(w, sheet_name="people", index=False)
    pd.DataFrame({"code":["X","Y","Z"],"amt":[10,20,30]}).to_excel(w, sheet_name="ledger", index=False)
res = read_all_sheets(p)
assert [r[0] for r in res] == ["people","ledger"], [r[0] for r in res]
assert res[0][1].shape[0]==2 and res[1][1].shape[0]==3
# round-trip export keeps both sheets
out = to_xlsx_multi([(n,df) for n,df,_ in res], TMP/"out.xlsx")
back = pd.ExcelFile(out).sheet_names
assert back == ["people","ledger"], back
print("per-sheet OK:", back)

# --- boolean guard: footnote flags stay categorical, real booleans convert
cases = {
    "flag_y": (["y","","y","y"], "categorical"),
    "codes":  (["y,v","y","y,v"], "TEXTUAL"),
    "consent":(["yes","no","yes"], "boolean"),
    "yn":     (["y","n","y","n"], "boolean"),
}
for name,(vals,exp) in cases.items():
    got = profile_column(pd.Series(vals), name).semantic_type
    if exp == "TEXTUAL":
        assert got in ("categorical","free_text","text"), f"{name}: not textual, got {got}"
    else:
        assert got == exp, f"{name}: expected {exp}, got {got}"
    print(f"bool guard OK: {name} -> {got}")
print("ALL PASSED")

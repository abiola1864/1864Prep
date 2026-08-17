import warnings; warnings.filterwarnings("ignore"); import pandas as pd, io, tempfile
from pathlib import Path
from engine.ingest import detect_orientation, read_csv_like, _transpose, read_excel
from engine.context import DatasetContext, ColumnContext, Ledger
from engine.toolkit import guess_gender, _name_column_score

TMP = Path(tempfile.mkdtemp())

# 1) orientation: normal / transposed / form
normal = [["name","age","city"],["Ada","30","Lagos"],["Bola","25","Kano"],["Uche","41","Abuja"]]
assert detect_orientation(normal) == "normal", detect_orientation(normal)
transposed = [["Field","p1","p2","p3","p4","p5","p6"],["name","Ada","Bola","Uche","Ola","Ife","Sam"],["city","Lagos","Kano","Abuja","Jos","Enugu","Yola"],["role","nurse","clerk","farmer","teacher","driver","trader"]]
print("transposed ->", detect_orientation(transposed))
form = [["Category","Description of Item","Cost",""],["Travel","flights","500",""],["","Sub-total","500",""],
        ["Research","","",""],["Other","","",""],["","Total","500",""],["Data Acquisition","","",""]]
print("form ->", detect_orientation(form))
assert detect_orientation(form) == "form"

# 2) CSV now handles multi-row header + orientation note + big-file note path
p = TMP/"t.csv"; p.write_text("BANNER LINE\n\nregion,sales,sales\n,q1,q2\nNorth,10,20\nSouth,30,40\n")
df, rep = read_csv_like(p, "csv")
print("csv cols:", list(df.columns), "| notes:", [n for n in rep.notes if "layout" in n])
assert any("layout detected" in n for n in rep.notes)

# 3) Context + Ledger record and surface every decision
led = Ledger()
led.note_safe("name","reformat","ada ","Ada", reason="trim + capitalise")
led.propose("state","reference_fix","Cros River","Cross River", reason="matched official list")
led.propose("age","flag","200","200", reason="out of range 0-120")
s = led.summary()
print("ledger summary:", s)
assert s["safe"]==1 and s["needs_approval"]==2
assert len(led.pending())==2 and led.to_list()[0]["safety"]=="safe"

# 4) gender name-column scoring prefers the real name column
df2 = pd.DataFrame({"member_id":["A1","A2","A3"],"full_name":["Ada Obi","Bola Eze","Uche Ali"],"amount":["10","20","30"]})
sc_name = _name_column_score("full_name", df2["full_name"].tolist())
sc_id   = _name_column_score("member_id", df2["member_id"].tolist())
sc_amt  = _name_column_score("amount", df2["amount"].tolist())
print("scores name/id/amt:", round(sc_name,2), round(sc_id,2), round(sc_amt,2))
assert sc_name > sc_id and sc_name > sc_amt
out, info = guess_gender(df2)   # no names-dataset -> should still identify the column
print("gender picked column:", info.get("column"))
assert info.get("column") == "full_name"
print("ALL PIPELINE FEATURE TESTS PASSED")

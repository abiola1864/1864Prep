import warnings; warnings.filterwarnings("ignore"); import pandas as pd, tempfile
from pathlib import Path
from engine.ingest import read_any
TMP=Path(tempfile.mkdtemp())

# a big messy real sheet + a tiny clean junk sheet + a near-empty copy:
# selection must prefer the big real one by DATA VOLUME, not density.
p=TMP/"multi.xlsx"
with pd.ExcelWriter(p) as w:
    big=pd.DataFrame({"S/N":range(1,201),"Name":["Person %d"%i for i in range(200)],
                      "State":["Lagos","Kano"]*100,"Amount":[100+i for i in range(200)]})
    big.to_excel(w,sheet_name="Sheet1",index=False)
    pd.DataFrame({"Name":["junk"],"Amount":["'=A1/0"]}).to_excel(w,sheet_name="Sheet1 (2)",index=False)
    pd.DataFrame({"x":[""]}).to_excel(w,sheet_name="copy",index=False)
df,rep=read_any(p)
assert rep.sheet=="Sheet1", "picked %r, expected the big real sheet"%rep.sheet
assert len(df)>=190
print("sheet selection prefers data volume:", rep.sheet, len(df), "rows")

# banner + embedded divider + real header lower down: header must be the real one
q=TMP/"divider.csv"
q.write_text("BIG TITLE BANNER\n\nS/N,Name,State,Amount\n>>> LAGOS <<<\n1,Ada,Lagos,100\n2,Bola,Kano,200\n>>> KANO <<<\n3,Uche,Kano,300\n")
d2,r2=read_any(q)
assert list(d2.columns)==["S/N","Name","State","Amount"], list(d2.columns)
assert len(d2)==3, "dividers should be dropped, got %d rows"%len(d2)
print("divider handling OK:", list(d2.columns), len(d2), "rows")
print("ALL SHEET/DIVIDER TESTS PASSED")

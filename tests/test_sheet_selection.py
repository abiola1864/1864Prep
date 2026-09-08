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

def test_general_messy_shapes():
    import pandas as pd, tempfile
    from pathlib import Path
    from engine.ingest import read_any
    T=Path(tempfile.mkdtemp())
    # transposed
    q=T/"b.csv"; q.write_text("field,r1,r2,r3,r4,r5\nproduct,Pump,Valve,Pipe,Motor,Gasket\nregion,N,S,E,W,N\nunits,10,20,30,40,50\n")
    d2,_=read_any(q); assert "product" in [str(c).lower() for c in d2.columns]
    # banner + 2-row header
    r=T/"c.csv"; r.write_text("MINISTRY EXPORT\n\nStudent,Score,Score\n,Term1,Term2\nAda,80,90\nBix,70,60\n")
    d3,_=read_any(r); assert str(list(d3.columns)[0])=="Student" and any("Term" in str(c) for c in d3.columns)
    # ALL-CAPS 1-cell dividers (not '>>>')
    s=T/"d.csv"; s.write_text("id,name,town,fee\nNORTHERN ZONE\n1,Ada,Kano,100\n2,Bola,Jos,200\nSOUTHERN ZONE\n3,Uche,Aba,300\n")
    d4,_=read_any(s); assert len(d4)==3 and list(d4.columns)==["id","name","town","fee"]
    # clean file untouched
    t=T/"e.csv"; t.write_text("name,age,city\nAda,30,Lagos\nBola,25,Kano\n")
    d5,_=read_any(t); assert list(d5.columns)==["name","age","city"] and len(d5)==2
    # sparse-but-real multi-cell row kept
    u=T/"f.csv"; u.write_text("id,name,phone,email,note\n1,Ada,080,a@x.com,hi\n2,,,,real\n3,Uche,081,u@x.com,ok\n")
    d6,_=read_any(u); assert len(d6)==3
    print("general messy shapes OK")

test_general_messy_shapes()

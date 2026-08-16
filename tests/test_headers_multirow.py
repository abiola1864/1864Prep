import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
from engine.ingest import read_csv_like, _find_data_start, _compose_multi

# 1) banner + 2-row header
rows = [["MY AGENCY EXPORT","","",""],["","","",""],
        ["Region","Sales","","Staff"],["","total","part","total"],
        ["North","100","20","5"],["South","200","40","8"]]
assert _find_data_start(rows) == 4, _find_data_start(rows)
n = _compose_multi([rows[2], rows[3]])
print("2-row:", n)
assert n == ["Region","Sales - total","Sales - part","Staff - total"], n

# 2) single-row CSV untouched
p = Path("/tmp/plain.csv"); p.write_bytes(b"name,age,city\nAda,30,Lagos\nBse,25,Kano\n")
df, rep = read_csv_like(p, "csv")
assert list(df.columns) == ["name","age","city"], list(df.columns)

# 3) forward-filled parent across merged span
lv = [["A","Group X","","",""],["id","q1","q2","q3",""]]
print("merged:", _compose_multi(lv))
print("ALL PASSED")

"""Data Toolkit: duplicates, match (auto-key), validate, summarise, dedupe, exports."""
import sys, tempfile
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import toolkit as tk          # noqa
from engine import exporters as ex        # noqa


def test_find_and_remove_duplicates():
    df = pd.DataFrame([{"id":"1","n":"Musa"},{"id":"1","n":"Musa"},{"id":"2","n":"Ada"}])
    dup, s = tk.find_duplicates(df); assert s["rows_involved"] == 2
    clean, s2 = tk.dedupe_file(df); assert s2["remaining"] == 2


def test_match_auto_key():
    a = pd.DataFrame({"NIN":["11","22","33"],"age":[30,40,50]})
    b = pd.DataFrame({"nin":["22","33","44"],"lga":["Ikeja","Oredo","Uyo"]})
    m, s = tk.match_files([a,b], how="inner")
    assert s["key_detected"] == "NIN" and s["rows"] == 2


def test_validate_and_summarise():
    df = pd.DataFrame({"email":["a@b.com","bad","c@d.io"], "name":["A","","C"]})
    rep, s = tk.validate(df); assert s["issues"] >= 1
    summ, s2 = tk.summarise(df); assert s2["columns"] == 2 and "missing_%" in summ.columns


def test_exports_all_formats():
    df = pd.DataFrame({"a":[1,2],"b":["x","y"]})
    for fmt in ["csv","xlsx","docx"]:
        p = Path(tempfile.mkdtemp()) / f"o.{fmt}"
        ex.export(df, fmt, p, title="T")
        assert p.exists() and p.stat().st_size > 0



def test_compare_combine_anonymise_quickclean():
    import pandas as pd
    a = pd.DataFrame({"id":["1","2","3"],"name":["Ada","Musa","Ngozi"]})
    b = pd.DataFrame({"id":["2","3","4"],"name":["Musa","NGOZI","Emeka"]})
    _, s = tk.compare_files([a,b]); assert s["added"]==1 and s["removed"]==1 and s["changed"]==1
    r, s = tk.combine_files([a,b]); assert s["rows"]==6 and "_source_file" in r.columns
    df = pd.DataFrame({"NIN":["12345678901","22345678901"],"name":["Musa Bello","Ada Obi"],"age":["30","41"]})
    r, s = tk.anonymise(df); assert "NIN" in s["which"] and "age" not in s["which"]
    q = pd.DataFrame({"Phone":["08031234567","0806 999 0000"]})
    r, s = tk.quick_clean(q); assert r.iloc[0]["Phone"].startswith("+234")


if __name__ == "__main__":
    fns = [v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns: fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} toolkit tests passed.")

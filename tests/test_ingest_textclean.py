"""Tests for robust ingestion (CSV/JSON/Excel/PDF) and natural-language cleaning."""
import sys, json
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.ingest import read_any, read_csv_like  # noqa
from engine.textclean import normalize_text, normalize_missing, detect_language, extract  # noqa
from engine import get_transform  # noqa

TMP = Path("/tmp/1864_ingest"); TMP.mkdir(exist_ok=True)


def test_csv_banner_ragged_semicolon():
    # two banner rows, semicolon delimiter, a ragged row
    p = TMP / "messy.csv"
    p.write_text("Ministry of Health — export\nGenerated 2026-01-01\n"
                 "id;full name;state\n1;ADA LOVELACE;Lagos\n2;musa;Kano;EXTRA\n3;;Kastina\n",
                 encoding="utf-8")
    df, rep = read_any(p)
    assert list(df.columns) == ["id", "full name", "state"]
    assert rep.delimiter == ";" and rep.header_row == 3
    assert len(df) == 3 and df.iloc[1]["state"] == "Kano"   # ragged trimmed to width


def test_json_nested_flatten():
    p = TMP / "nested.json"
    json.dump([{"id": 1, "person": {"name": "Ada", "age": 30}},
               {"id": 2, "person": {"name": "Musa", "age": 41}}], p.open("w"))
    df, rep = read_any(p)
    assert "person.name" in df.columns and "person.age" in df.columns
    assert df.iloc[0]["person.name"] == "Ada"


def test_excel_multi_sheet_picks_fullest():
    p = TMP / "book.xlsx"
    with pd.ExcelWriter(p) as w:
        pd.DataFrame({"note": ["ignore me"]}).to_excel(w, sheet_name="cover", index=False)
        pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]}).to_excel(w, sheet_name="data", index=False)
    df, rep = read_any(p)
    assert rep.sheet == "data" and len(df) == 3


def test_pdf_table_roundtrip():
    try:
        from fpdf import FPDF
    except Exception:
        print("  (fpdf2 not installed — skipping PDF assertion)"); return
    p = TMP / "table.pdf"
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Helvetica", size=11)
    rows = [["id", "state"], ["1", "Lagos"], ["2", "Kano"], ["3", "Rivers"]]
    for r in rows:
        for c in r:
            pdf.cell(40, 8, c, border=1)
        pdf.ln()
    pdf.output(str(p))
    df, rep = read_any(p)
    assert rep.kind == "pdf" and rep.pages == 1
    assert "state" in [str(c).lower() for c in df.columns] or "state" in df.to_string().lower()


def test_textclean_normalises():
    assert normalize_text("  caf\u00e9\u200b  ") == "café"
    assert normalize_text("\u201cquoted\u201d \u2014 dash") == '"quoted" - dash'
    for junk in ["N/A", "n.a.", "NULL", "-", "unknown", ""]:
        assert normalize_missing(junk) == ""
    assert normalize_missing("Lagos") == "Lagos"


def test_textclean_extract():
    txt = "call 0803 123 4567 or +2348069990000, email a@b.com; born 12/03/1990"
    assert "a@b.com" in extract("email", txt)
    assert any("0803" in p for p in extract("phone", txt))
    assert "12/03/1990" in extract("date", txt)


def test_text_clean_transform():
    tf = get_transform("text_clean")
    s = pd.Series(["  N/A ", "caf\u00e9\u200b", "  двойной  space "])
    res = tf.run(s, "notes", "notes")
    out = list(res.series)
    assert out[0] == "" and out[1] == "café"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} ingest/textclean tests passed.")

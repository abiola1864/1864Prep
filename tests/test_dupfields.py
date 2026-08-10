"""Duplicate/versioned column detection by value overlap (not header noise)."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.dupfields import find_duplicate_fields   # noqa


def test_prefixed_and_blank_header_duplicates_group():
    df = pd.DataFrame({
        "RAW_DATA_name": ["Wazobia","Binukonu","Oja Oba","Thomas","Owode"],
        "ADRIENNE_name": ["Wazobia","Binukonu","Oja Oba","Thomas","Owode"],
        "column_3_no_header": ["Wazobia","Binukonu","Oja Oba","Thomas","Owode"],
        "unrelated": ["a","b","c","d","e"],
    })
    groups = find_duplicate_fields(df)
    assert len(groups) == 1
    assert set(groups[0]["columns"]) == {"RAW_DATA_name","ADRIENNE_name","column_3_no_header"}
    assert "no header" not in groups[0]["keep"].lower()   # prefer a real header to keep


def test_repeating_group_not_flagged():
    # different captures of the same measurement share a name but hold DIFFERENT values
    df = pd.DataFrame({
        "gps_lat_1": ["6.1","6.2","6.3","6.4","6.5"],
        "gps_lat_2": ["6.9","6.8","6.7","6.6","6.0"],
        "gps_lat_3": ["7.1","7.2","7.3","7.4","7.5"],
    })
    assert find_duplicate_fields(df) == []


if __name__ == "__main__":
    fns=[v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns: fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} duplicate-field tests passed.")

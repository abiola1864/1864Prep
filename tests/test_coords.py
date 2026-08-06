"""Coordinates: header-aware detection, DMS->decimal, ranges, geopoint split."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import get_transform  # noqa
from engine.profile import profile_column  # noqa
from engine.reshape import split_geopoint  # noqa


def test_header_drives_lat_long():
    assert profile_column(pd.Series(["6.45", "6.52", "6.60"]), "lat").semantic_type == "latitude"
    assert profile_column(pd.Series(["3.39", "3.40", "-3.1"]), "long").semantic_type == "longitude"
    assert profile_column(pd.Series(["6.45, 3.39", "6.5; 3.4"]), "gps_coord").semantic_type == "geopoint"
    # no coordinate hint -> stays numeric
    assert profile_column(pd.Series(["12.5", "3.4", "88.1"]), "weight").semantic_type == "numeric"


def test_lat_long_transforms():
    lat = get_transform("latitude"); lon = get_transform("longitude")
    assert lat.apply_value("6\u00b027'N")[0] == "6.45"
    assert lon.apply_value("30.123W")[0] == "-30.123"
    assert lat.apply_value("200")[1] is True       # out of range flagged
    assert lon.apply_value("-200")[1] is True


def test_numeric_keeps_negative():
    n = get_transform("numeric")
    assert n.apply_value("-81.0")[0] == "-81"
    assert n.apply_value("-99")[0] == "-99"
    assert n.apply_value("(200)")[0] == "-200"


def test_geopoint_split():
    d = split_geopoint(pd.Series(["6.45, 3.39", "(6.52; 3.37)"]))
    assert list(d.iloc[0]) == ["6.45", "3.39"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} coordinate tests passed.")

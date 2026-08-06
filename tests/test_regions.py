"""The engine is generic; a country is a swappable region pack, not code."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import regions  # noqa
from engine import get_transform  # noqa


def test_region_lookup_and_fallback():
    assert regions.get_region("ng").phone_region == "NG"
    assert regions.get_region("ng").date_order == "DMY"
    assert regions.get_region("does-not-exist").key == "generic"   # safe fallback
    assert "ng" in regions.list_regions() and "generic" in regions.list_regions()


def test_phone_follows_active_region():
    regions.set_active_region("ng")
    try:
        out, flagged, _ = get_transform("phone").apply_value("08031234567")
        assert out == "+2348031234567" and not flagged
    finally:
        regions.set_active_region("generic")


def test_date_order_follows_active_region():
    regions.set_active_region("ng")           # day-first
    try:
        out, flagged, _ = get_transform("date_iso").apply_value("3/9/1990")
        assert out == "1990-09-03" and not flagged     # 3 Sept, not 9 March
    finally:
        regions.set_active_region("generic")


def test_generic_region_has_no_place_lists():
    regions.set_active_region("generic")
    ref = regions.load_reference()
    assert ref["gazetteers"] is None          # geo detection simply won't fire
    regions.set_active_region("ng")
    ref = regions.load_reference()
    assert ref["gazetteers"] and "state" in ref["gazetteers"]
    regions.set_active_region("generic")


def test_custom_region_can_be_registered():
    from regions.base import Region
    regions.register_region(Region(key="ke", name="Kenya", phone_region="KE", date_order="DMY"))
    assert regions.get_region("ke").phone_region == "KE"
    regions.set_active_region("ke")
    try:
        out, flagged, _ = get_transform("phone").apply_value("0712345678")
        assert out.startswith("+254") and not flagged      # Kenyan number, same engine
    finally:
        regions.set_active_region("generic")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} region tests passed.")

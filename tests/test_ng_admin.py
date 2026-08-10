"""Nigeria states + LGAs: full-set validation with typo tolerance and flags."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ng_admin as NG   # noqa


def test_state_resolution_and_typos():
    assert NG.resolve_state("Katsina") == "Katsina"
    assert NG.resolve_state("Cros River") == "Cross River"     # typo auto-fixed
    assert NG.resolve_state("Akwa-Ibom") == "Akwa Ibom"
    assert NG.resolve_state("FCT") == "Federal Capital Territory"
    assert NG.resolve_state("Abuja") == "Federal Capital Territory"


def test_lga_validation_and_level_mismatch():
    assert NG.validate_lga_value("Ikeja")["kind"] == "lga"
    assert NG.validate_lga_value("Bakory")["canonical"] == "Bakori"        # typo
    assert NG.validate_lga_value("Lagos")["kind"] == "is_state"            # wrong level
    r = NG.validate_lga_value("Computer Village")
    assert r["kind"] == "unknown"                                          # city/community
    k = NG.validate_lga_value("Kastna")
    assert k["kind"] == "unknown" and k.get("suggestion") == "Katsina"     # flagged, not silently changed


def test_coverage():
    d = NG._data()
    assert len(d["states"]) == 37 and len(d["all_lgas"]) >= 760


def test_admin_suffix_and_slash_stripping():
    assert NG.resolve_lga("Ikeja LGA") == "Ikeja"
    assert NG.resolve_lga("Surulere Local Council") == "Surulere"
    assert NG.resolve_lga("Kosofe Local Government Area") == "Kosofe"
    # first name taken before a slash
    assert NG.resolve_state("Lagos / Ikeja") == "Lagos"

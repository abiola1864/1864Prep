"""Alignment tests: assert the Python transforms reproduce the NCC MASTER R
behaviour on the exact example strings that appear in the R script (and its
comments). If any of these fail, the port has diverged from the R logic.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import get_transform  # noqa: E402

REF_STATES = "reference/ng_states.json"


def one(name, value, **params):
    res = get_transform(name, **params).run(pd.Series([value]), "s", "t")
    return res.series.iloc[0], res.n_flagged > 0


# ---- STATE: parenthesis-first algorithm + full map ----
def test_state_paren_stripping_and_quirks():
    assert one("state_ng", "Kastina", reference=REF_STATES) == ("KATSINA", False)
    assert one("state_ng", "Port Harcourt", reference=REF_STATES) == ("RIVERS", False)
    assert one("state_ng", "Benin(Edo)", reference=REF_STATES) == ("EDO", False)
    # QUIRK (documented): parens stripped first, so the city outside the parens
    # decides the match. 'Onitsha(Abia)' -> 'Onitsha' -> ANAMBRA, not ABIA.
    assert one("state_ng", "Onitsha(Abia)", reference=REF_STATES) == ("ANAMBRA", False)
    # 'Ibadan(Osun)' -> 'Ibadan' -> OYO, not OSUN.
    assert one("state_ng", "Ibadan(Osun)", reference=REF_STATES) == ("OYO", False)
    # Sentinel + unknown -> flagged
    assert one("state_ng", "No State", reference=REF_STATES)[1] is True
    assert one("state_ng", "Atlantis", reference=REF_STATES)[1] is True


# ---- LGA: 5-step pipeline ----
def test_lga_pipeline():
    assert one("lga_ncc", "OSHODIISOLO")[0] == "OSHODI-ISOLO"
    assert one("lga_ncc", "ADOODOOTA")[0] == "ADO-ODO/OTA"
    assert one("lga_ncc", "Kano")[0] == "KANO MUNICIPAL"
    assert one("lga_ncc", "abuja")[0] == "ABUJA MUNICIPAL"
    assert one("lga_ncc", "Shagamu")[0] == "SAGAMU"
    # suffix stripping
    assert one("lga_ncc", "Ikeja Municipal Area Council")[0] == "IKEJA"
    # junk -> UNKNOWN + flagged
    assert one("lga_ncc", "12345") == ("UNKNOWN", True)
    assert one("lga_ncc", "REFUSED") == ("UNKNOWN", True)


# ---- DATES: the exact formats named in parse_ymd_fallback_dt comments ----
def test_date_formats():
    p = {"min_year": 2025, "max_year": 2026, "dayfirst": False}
    assert one("date_iso", "2026-02-08 05:59:39", **p)[0] == "2026-02-08"
    assert one("date_iso", "1/1/2026 15:32", **p)[0] == "2026-01-01"   # mdy_hm
    assert one("date_iso", "3/9/26 8:29", **p)[0] == "2026-03-09"      # 2-digit yr, month-first
    assert one("date_iso", "2/2/2026", **p)[0] == "2026-02-02"         # mdy
    assert one("date_iso", "2026-01-01", **p)[0] == "2026-01-01"       # ymd
    assert one("date_iso", "Monday, March 23, 2026", **p)[0] == "2026-03-23"
    # out-of-range gets nulled + flagged (record kept)
    assert one("date_iso", "2020-05-05", **p) == ("", True)


# ---- PROVIDER ----
def test_provider():
    assert one("provider", "AIRTEL")[0] == "Airtel"
    assert one("provider", "EMTS")[0] == "T2"
    assert one("provider", "FIBREONE")[0] == "Fiberone"
    assert one("provider", "SomeRandomCo")[1] is True   # not in known list -> flagged
    assert one("provider_type", "MTN")[0] == "MNO"
    assert one("provider_type", "Spectranet")[0] == "ISP"


# ---- CATEGORY ----
def test_category():
    assert one("category", "DATA DEPLETION - fast usage")[0] == "Data Depletion"
    assert one("category", "Quality of Service (Voice)")[0] == "Quality of Service/Experience (Voice)"
    assert one("category", "Sim card Replacement")[0] == "SIM Replacement"
    assert one("category", "Billing")[0] == "Billing"
    assert one("category", "Others")[0] == "Others"


# ---- TICKET SOURCE ----
def test_ticket_source():
    assert one("ticket_source", "Inbound Call")[0] == "Call Center"
    assert one("ticket_source", "WhatsApp")[0] == "Digital"
    assert one("ticket_source", "Walk-in Store")[0] == "Walk-in"
    assert one("ticket_source", "SRC06-web")[0] == "src06"
    assert one("ticket_source", "12345")[0] == "Other"


# ---- SLA ----
def test_sla():
    assert one("sla", "Yes")[0] == "Yes"
    assert one("sla", "Outside SLA")[0] == "No"
    assert one("sla", "Resolved outside sla")[0] == "No"
    assert one("sla", "In View") == ("", True)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} R-alignment tests passed.")

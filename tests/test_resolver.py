"""Tests for the robust resolver: it must handle spellings that are in NO
dictionary, and it must abstain (not guess) on values that need a gazetteer."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import get_transform  # noqa: E402
from engine.resolve import EntityResolver  # noqa: E402

CANON = "reference/ng_states_canonical.json"
OFFICIAL = ["ABIA","ADAMAWA","AKWA IBOM","ANAMBRA","BAUCHI","BAYELSA","BENUE","BORNO",
"CROSS RIVER","DELTA","EBONYI","EDO","EKITI","ENUGU","FCT","GOMBE","IMO","JIGAWA","KADUNA",
"KANO","KATSINA","KEBBI","KOGI","KWARA","LAGOS","NASARAWA","NIGER","OGUN","ONDO","OSUN","OYO",
"PLATEAU","RIVERS","SOKOTO","TARABA","YOBE","ZAMFARA"]


def test_resolves_unseen_misspellings():
    r = EntityResolver(OFFICIAL)
    # None of these appear in any alias list; all should resolve to the right state.
    for messy, expected in [("Kastina","KATSINA"),("kadna","KADUNA"),("Plateu","PLATEAU"),
                            ("Phlateau","PLATEAU"),("Nassarawa","NASARAWA"),("Zamfra","ZAMFARA"),
                            ("Adamewa","ADAMAWA"),("Akwaibom","AKWA IBOM"),("cross rivers","CROSS RIVER")]:
        m = r.resolve(messy)
        assert m.canonical == expected, f"{messy} -> {m.canonical} (want {expected})"


def test_abstains_on_cities():
    # Cities are NOT states; string similarity should abstain rather than guess.
    r = EntityResolver(OFFICIAL)
    for city in ["Ibadan", "Port Harcourt", "Onitsha", "xyz123"]:
        m = r.resolve(city)
        assert m.band == "unresolved", f"{city} should be unresolved, got {m.band}"


def test_resolve_transform_bands():
    r = get_transform("resolve", reference=CANON)
    s = pd.Series(["Kastina", "kadna", "Ibadan", "LAGOS"])
    res = r.run(s, "State", "State")
    out = list(res.series)
    assert out[0] == "KATSINA"      # high, auto
    assert out[1] == "KADUNA"       # high, auto
    assert out[2] == "Ibadan"       # unresolved -> raw kept, flagged
    assert out[3] == "LAGOS"        # exact
    assert res.n_flagged == 1       # only Ibadan


def test_distinct_only():
    # Resolving works on the distinct set; duplicates cost nothing extra.
    r = EntityResolver(OFFICIAL)
    values = ["Kastina"] * 1000 + ["kadna"] * 1000
    d = r.resolve_distinct(values)
    assert len(d) == 2  # only two distinct strings resolved


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} resolver tests passed.")

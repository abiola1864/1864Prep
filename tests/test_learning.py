"""Tests for the correction memory, per-field prediction, and the learning loop."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.knowledge import CorrectionStore  # noqa: E402
from engine.predict import predict_field  # noqa: E402
from engine.resolve import EntityResolver  # noqa: E402

STATES = ["ABIA","ANAMBRA","RIVERS","OYO","LAGOS","FCT","AKWA IBOM","ENUGU","KATSINA","KADUNA"]
GAZ = {"ng_state": STATES}
TMP = "knowledge/_test_user.json"


def _fresh_store():
    p = Path(TMP)
    if p.exists():
        p.unlink()
    return CorrectionStore(user_path=TMP)


def test_shared_corrections_are_known():
    s = _fresh_store()
    assert s.lookup("ng_state", "Port Harcourt") == ("canonical", "RIVERS")
    assert s.lookup("ng_state", "Ibadan") == ("canonical", "OYO")
    assert s.lookup("ng_state", "Onitsha") == ("canonical", "ANAMBRA")


def test_conflicts_are_surfaced_not_guessed():
    s = _fresh_store()
    kind, cand = s.lookup("ng_state", "Abuja(Jos)")
    assert kind == "conflict" and set(cand) == {"FCT", "PLATEAU"}


def test_resolver_uses_memory_first():
    s = _fresh_store()
    r = EntityResolver(STATES, memory=s.memory("ng_state"))
    m = r.resolve("Port Harcourt")
    assert m.canonical == "RIVERS" and m.method == "learned"
    # a novel misspelling still handled by fuzzy
    assert r.resolve("Lasgos").canonical == "LAGOS"


def test_learning_persists():
    s = _fresh_store()
    assert s.lookup("ng_state", "Uyo") == (None, None)     # unknown at first
    s.learn("ng_state", "Uyo", "AKWA IBOM")
    assert s.lookup("ng_state", "Uyo") == ("canonical", "AKWA IBOM")
    # reload from disk -> still known
    s2 = CorrectionStore(user_path=TMP)
    assert s2.lookup("ng_state", "Uyo") == ("canonical", "AKWA IBOM")
    Path(TMP).unlink()


def test_predict_uses_header_prior_and_memory():
    s = _fresh_store()
    # header 'Sex' -> Gender even with coded values
    p = predict_field(pd.Series(["M", "F", "1", "2"] * 10), "Sex", s, GAZ)
    assert p.predicted_name == "Gender" and p.semantic_type == "gender"
    # header 'Email' -> email even if a bad value drags the format rate down
    p = predict_field(pd.Series(["a@x.com", "b@y.org", "bad", "c@z.net"] * 8), "Email", s, GAZ)
    assert p.semantic_type == "email"
    # 'State of Origin' with cities resolves via learned memory -> geo
    p = predict_field(pd.Series(["Port Harcourt", "Ibadan", "Onitsha", "Lagos"] * 10),
                      "State of Origin", s, GAZ)
    assert p.predicted_name == "State" and p.semantic_type == "geo"
    assert p.details["learned"] >= 3
    # 11-digit id asks the NIN/BVN disambiguation question
    p = predict_field(pd.Series([f"{10000000000 + i:011d}" for i in range(40)]), "NIN", s, GAZ)
    assert p.semantic_type == "identifier"
    assert any("NIN" in q and "BVN" in q for q in p.questions)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} learning tests passed.")

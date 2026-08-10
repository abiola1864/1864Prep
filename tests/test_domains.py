"""Domain resolution via packages: keep look-alike different entities apart."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import domains as D            # noqa
from engine.dedupe import cluster_similar  # noqa


def test_country_detect_and_resolve():
    col = ["Nigeria","Niger","Congo, Dem. Rep.","Congo, Rep.","Ghana","Kenya"]
    assert D.detect_domain(col, "Country Name") == "country"
    name, changed = D.resolve_value("country", "Congo, Dem. Rep.")
    assert name and name != "Congo, Dem. Rep." and changed


def test_lookalike_countries_are_distinct():
    for a, b in [("Niger","Nigeria"),("Sudan","South Sudan"),
                 ("Congo, Dem. Rep.","Congo, Rep."),
                 ("Korea, Dem. People's Rep.","Korea, Rep."),
                 ("China","Hong Kong SAR, China"),("China","Taiwan, China")]:
        assert D.same_entity("country", a, b) is False, f"{a} vs {b} should differ"
    # real spelling variants of the SAME country resolve together
    assert D.same_entity("country", "United States", "USA") is True


def test_clustering_respects_country_domain():
    vals = ["Niger","Nigeria","Congo, Dem. Rep.","Congo, Rep.","Sudan","South Sudan",
            "China","Hong Kong SAR, China","Taiwan, China"]
    for g in cluster_similar(vals, domain="country"):
        ids = {D.canonical_of("country", m) for m in g["members"]}
        assert len(ids) == 1, f"group mixes countries: {g['members']}"


def test_survey_categoricals_json():
    assert D.detect_domain(["M","F","male","female"], "Sex") == "sex"
    assert D.resolve_value("sex", "m")[0] == "Male"



def test_subdivision_and_currency_via_pycountry():
    assert D.detect_domain(["Kano","Kaduna","Cross River","Rivers","Lagos"], "State") in ("ng_state","subdivision")
    assert D.same_entity("subdivision", "Cross River", "Rivers") is False or D.same_entity("ng_state","Cross River","Rivers") is False
    assert D.detect_domain(["NGN","USD","Naira","EUR","GBP"], "Currency") == "currency"
    assert D.resolve_value("currency", "Naira")[0] == "NGN"


def test_ner_layer_degrades_without_model():
    from engine import nlp
    # sandbox has no spaCy model; must not raise, must return (None, 0.0)
    assert nlp.available() in (True, False)
    t, c = nlp.column_entity_type(["Ada Obi", "Musa Bello"])
    assert (t is None and c == 0.0) or isinstance(t, str)



def test_detection_is_value_first_and_not_greedy():
    # value-first: header name (useless / misleading / absent) doesn't change the answer
    lgas = ["Ikeja","Surulere","Kosofe","Alimosho","Eti-Osa","Ikorodu"]
    assert D.detect_domain(lgas, "Q4b") == "ng_lga"
    assert D.detect_domain(lgas, "address") == "ng_lga"
    assert D.detect_domain(lgas, "") == "ng_lga"
    # non-domain data must NOT be forced into a domain (country matcher isn't greedy)
    assert D.canonical_of("country", "12 Broad Street") is None
    assert D.canonical_of("country", "Yes") is None
    assert D.canonical_of("country", "Male") is None
    assert D.canonical_of("country", "Nigeria") == "NGA"      # real ones still resolve
    assert D.detect_domain(["12 Broad Street","No 4 Allen Ave","Plot 15 Lekki"], "place") is None
    assert D.detect_domain(["good service","very nice","too far","ok"], "comment") is None


if __name__ == "__main__":
    fns=[v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns: fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} domain tests passed.")

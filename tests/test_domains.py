"""Domain packs: resolve entities and keep look-alike different entities apart."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import domains as D          # noqa
from engine.dedupe import cluster_similar  # noqa


def test_detect_and_resolve():
    assert D.detect_domain(["Nigeria","Niger","Ghana","naija","DRC"], "Country") == "country"
    assert D.resolve_value("country","naija")[0] == "Nigeria"
    assert D.resolve_value("country","DRC")[0] == "Congo, Dem. Rep."
    assert D.detect_domain(["M","F","male","female"], "Sex") == "sex"


def test_lookalikes_are_different_entities():
    for a,b in [("Niger","Nigeria"),("Iceland","Ireland"),("Guinea","Guinea-Bissau"),
                ("Congo, Dem. Rep.","Congo, Rep.")]:
        assert D.same_entity("country",a,b) is False
    assert D.same_entity("country","Nigeria","naija") is True


def test_clustering_respects_domain():
    vals = ["Niger","Nigeria","Nigeria","naija","Iceland","Ireland","Guinea","Guinea-Bissau"]
    # without domain, string similarity would group Niger+Nigeria; with domain it must not
    groups = cluster_similar(vals, domain="country")
    for g in groups:
        canon = {D.canonical_of("country", m) for m in g["members"]}
        assert len(canon) == 1, f"group mixes entities: {g['members']}"


if __name__ == "__main__":
    fns=[v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns: fn(); print("ok:", fn.__name__)
    print(f"\nAll {len(fns)} domain tests passed.")

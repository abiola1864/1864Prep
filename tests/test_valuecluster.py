import warnings; warnings.filterwarnings("ignore")
from engine.valuecluster import cluster_values
def test_clusters_variants_instantly():
    m=cluster_values(["Lagos","lagos","LAGOS ","Kano","kano","Katsina","katsina","Oyo"])
    keys={k.lower() for k in m}
    assert "lagos" in keys and "kano" in keys
    print("cluster:", m)
test_clusters_variants_instantly()
print("VALUECLUSTER TEST PASSED")

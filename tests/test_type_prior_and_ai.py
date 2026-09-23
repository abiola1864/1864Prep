import warnings; warnings.filterwarnings("ignore"); import pandas as pd
from engine.profile import profile_column
from engine.ai_client import classify_endpoint, parse_suggestion, ask

def test_type_prior_breaks_ties_only():
    s=pd.Series(["12","7","19","23","8","14","31","5","27"])
    assert profile_column(s,"code",type_prior={"identifier"}).semantic_type=="identifier"
    assert profile_column(s,"code",type_prior={"numeric"}).semantic_type=="numeric"
    # strong signals never overridden
    assert profile_column(pd.Series(["a@x.com","b@y.com","c@z.com"]),"c",type_prior={"identifier"}).semantic_type=="email"
    assert profile_column(pd.Series(["2021-01-01","2021-02-01","2021-03-01"]),"d",type_prior={"numeric"}).semantic_type=="date"
    print("type prior: ties only, strong signals safe")

def test_ai_local_vs_cloud():
    assert classify_endpoint("ollama","http://127.0.0.1:11434","llama3.2")["leaves_device"] is False
    assert classify_endpoint("ollama","","gpt-oss:120b-cloud")["leaves_device"] is True
    assert classify_endpoint("openai","","gpt-4o-mini")["leaves_device"] is True
    print("ai client: local vs cloud classified correctly")

def test_ai_fails_gracefully():
    r=ask("type?","ollama","http://127.0.0.1:11434","llama3.2",timeout=2)
    assert r["ok"] is False and "error" in r and r["leaves_device"] is False
    assert parse_suggestion("Looks like an identifier")["suggestion"]=="identifier"
    print("ai client: graceful failure + parse")

test_type_prior_breaks_ties_only()
test_ai_local_vs_cloud()
test_ai_fails_gracefully()
print("ALL TYPE-PRIOR + AI TESTS PASSED")

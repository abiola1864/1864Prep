import warnings; warnings.filterwarnings("ignore")
from engine.ai_privacy import build_column_query, looks_sensitive, default_mode, is_full_dataset, MODES

# a phone-like column is sensitive -> masked by default, shape kept, content hidden
q = build_column_query("phone_number", ["08031234567","08127654321","08031234567","0805"])
print("phone mode:", q["mode"], "| sent:", q["sent_values"])
assert q["mode"] == "masked"
assert all(ch in "9-" or not ch.isdigit() for v in q["sent_values"] for ch in v)  # no real digits
assert q["row_count_hidden"] is True
assert q["distinct_sampled"] == 3                      # distinct, not row count

# a plain category column -> samples, per-column only
q2 = build_column_query("region", ["North","South","North","East"], task="canonical")
print("region:", q2["sent_values"], "| q:", q2["question"][:40])
assert q2["sent_values"] == ["North","South","East"]
assert is_full_dataset(q2) is False                    # single-column guarantee holds

# labels_only sends NO values at all
q3 = build_column_query("national_id", ["A1","B2"], mode="labels_only")
assert q3["sent_values"] == []
print("labels_only sends nothing:", q3["sent_values"])

# shapes mode -> just patterns
q4 = build_column_query("bvn", ["12345678901","22345678902"], mode="shapes")
print("shapes:", q4["sent_values"])
assert all(s.startswith("[") for s in q4["sent_values"])
print("ALL AI-PRIVACY TESTS PASSED")

"""Embedding abstraction: always usable, honest about the active backend."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import embeddings as E   # noqa


def test_embedder_always_available_and_normalised():
    emb = E.get_embedder()
    assert emb.backend in ("sentence-transformers", "model2vec", "lexical")
    V = E.embed(["Ikeja market", "Ikeja markt", "phone"])
    # self-similarity ~1, typo pair high, unrelated low
    assert E.cosine(V[0], V[0]) > 0.99
    assert E.cosine(V[0], V[1]) > 0.5
    assert E.cosine(V[0], V[2]) < 0.4


def test_semantic_path_gated_honestly():
    # lexical fallback must report itself as NOT semantic, so callers don't fake synonymy
    if not E.is_semantic():
        assert E.get_embedder().backend == "lexical"
    pairs = E.semantic_pairs(["Groceries", "Groceriess", "phone number"], threshold=0.6)
    assert any({"Groceries", "Groceriess"} == {a, b} for a, b, _ in pairs)

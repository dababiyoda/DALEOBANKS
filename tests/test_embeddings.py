"""Tests for the embedding provider layer: hash bedrock, openai with
fallback, shadow mode, and dimension isolation in the index."""

from services.embeddings import EmbeddingService
from services.semantic_index import SemanticIndex


def _fake_openai(monkeypatch, calls, dim=8):
    """Deterministic stand-in for the OpenAI embedding call."""
    def fake(self, text):
        calls.append(text)
        # A crude but deterministic dense vector: char-code buckets.
        values = [0.0] * dim
        for i, ch in enumerate(text):
            values[i % dim] += ord(ch)
        norm = sum(v * v for v in values) ** 0.5
        return {i: v / norm for i, v in enumerate(values)}
    monkeypatch.setattr(EmbeddingService, "_openai_embed", fake)


def test_default_mode_is_offline_hash(tmp_path, monkeypatch):
    monkeypatch.delenv("EMBEDDINGS_PROVIDER", raising=False)
    index = SemanticIndex(path=str(tmp_path / "index.jsonl"))
    index.add("interconnection queues stall energy pilots")

    assert index.records()[0]["emb"]["provider"] == "hash"
    hits = index.search("energy pilots")
    assert hits and "queues" in hits[0]["text"]


def test_openai_mode_falls_back_to_hash_without_key(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    index = SemanticIndex(path=str(tmp_path / "index.jsonl"),
                          embeddings=EmbeddingService(mode="openai"))
    index.add("grid pilots need shared dispatch")

    # No key -> hash tag, and memory still works.
    assert index.records()[0]["emb"]["provider"] == "hash"
    assert index.search("grid pilots")


def test_openai_vectors_are_stored_and_reload_without_api_calls(tmp_path, monkeypatch):
    calls = []
    _fake_openai(monkeypatch, calls)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    path = str(tmp_path / "index.jsonl")
    service = EmbeddingService(mode="openai")
    index = SemanticIndex(path=path, embeddings=service)
    index.add("transmission reform beats generation subsidies")
    assert index.records()[0]["emb"]["provider"] == "openai"
    assert len(calls) == 1

    # Reload: the stored dense vector is reused — no new API call.
    reloaded = SemanticIndex(path=path, embeddings=EmbeddingService(mode="openai"))
    assert len(calls) == 1
    hits = reloaded.search("transmission reform")  # one call for the query
    assert len(calls) == 2
    assert hits and hits[0]["text"].startswith("transmission reform")


def test_provider_records_stay_searchable_after_provider_disappears(tmp_path, monkeypatch):
    calls = []
    _fake_openai(monkeypatch, calls)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    path = str(tmp_path / "index.jsonl")
    SemanticIndex(path=path, embeddings=EmbeddingService(mode="openai")).add(
        "evidence library recall compounds over time"
    )

    # Key removed: auto resolves to hash, but the memory is not lost —
    # the hash companion vector still matches.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    downgraded = SemanticIndex(path=path, embeddings=EmbeddingService(mode="auto"))
    hits = downgraded.search("evidence library recall")
    assert hits and "compounds" in hits[0]["text"]


def test_mixed_tag_index_searches_both_representations(tmp_path, monkeypatch):
    calls = []
    _fake_openai(monkeypatch, calls)
    path = str(tmp_path / "index.jsonl")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    index = SemanticIndex(path=path, embeddings=EmbeddingService(mode="auto"))
    index.add("hash era lesson about energy queues")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    index.add("openai era lesson about energy queues")

    tags = {r["emb"]["provider"] for r in index.records()}
    assert tags == {"hash", "openai"}
    hits = index.search("energy queues", k=5)
    assert len(hits) == 2  # both eras recalled, no dimension errors


def test_shadow_mode_serves_hash_but_exercises_openai(monkeypatch, tmp_path):
    calls = []
    _fake_openai(monkeypatch, calls)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    service = EmbeddingService(mode="shadow")
    vector, tag = service.embed("shadow window test")

    assert tag["provider"] == "hash"  # behavior unchanged
    assert calls == ["shadow window test"]  # but the new path was exercised
    assert service.shadow_stats["ok"] == 1

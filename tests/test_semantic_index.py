"""Tests for the durable semantic index and its memory wiring."""

from services.semantic_index import SemanticIndex


def _make_index(tmp_path):
    return SemanticIndex(path=str(tmp_path / "index.jsonl"))


def test_search_returns_most_related_memory(tmp_path):
    index = _make_index(tmp_path)
    index.add("Post proposals about renewable energy earlier in the day")
    index.add("Replies with citations outperform bare assertions")
    index.add("Thread posts about coordination mechanisms drive follows")

    results = index.search("renewable energy posting time", k=1)

    assert len(results) == 1
    assert "renewable energy" in results[0]["text"]
    assert results[0]["score"] > 0


def test_search_respects_k_and_min_score(tmp_path):
    index = _make_index(tmp_path)
    index.add("energy pilots need concrete KPIs")
    index.add("energy proposals should include rollback plans")
    index.add("totally unrelated gardening trivia")

    results = index.search("energy proposals", k=5)

    texts = [r["text"] for r in results]
    assert all("energy" in t for t in texts)
    assert "totally unrelated gardening trivia" not in texts


def test_index_persists_across_instances(tmp_path):
    path = str(tmp_path / "index.jsonl")
    first = SemanticIndex(path=path)
    first.add("quadratic funding pilots convert best on weekday mornings")

    reloaded = SemanticIndex(path=path)
    assert len(reloaded) == 1
    results = reloaded.search("quadratic funding", k=1)
    assert len(results) == 1
    assert "quadratic funding" in results[0]["text"]


def test_empty_query_and_empty_index_are_safe(tmp_path):
    index = _make_index(tmp_path)
    assert index.search("anything") == []
    index.add("a lesson")
    assert index.search("") == []


def test_memory_service_indexes_improvement_notes(tmp_path, monkeypatch):
    from services import semantic_index as semantic_index_module
    from services.memory import MemoryService

    isolated = SemanticIndex(path=str(tmp_path / "notes.jsonl"))
    monkeypatch.setattr(semantic_index_module, "_SHARED_INDEX", isolated)

    service = MemoryService()

    class FakeQuery:
        def count(self):
            return 0

        def order_by(self, *args, **kwargs):
            return self

        def limit(self, *args):
            return self

        def all(self):
            return []

    class FakeSession:
        def add(self, obj):
            self.added = obj

        def query(self, *args, **kwargs):
            return FakeQuery()

        def commit(self):
            pass

    service.add_improvement_note(FakeSession(), "post energy proposals at 9am ET")

    assert len(isolated) == 1
    assert service.search_similar_lessons("energy timing") == [
        "post energy proposals at 9am ET"
    ]

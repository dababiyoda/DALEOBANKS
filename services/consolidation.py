"""Dream consolidation: digital sleep that sharpens the agent's memory.

Over time the improvement-note store accumulates near-duplicate lessons
("post energy proposals earlier", "energy posts perform better in the
morning", ...). During idle hours this service clusters similar notes using
the same hashed bag-of-words embedding the semantic index uses, asks the LLM
to merge each cluster into one sharper lesson, and replaces the originals.
Every compression is recorded in the decision ledger, so consolidation is
auditable, and the LLM path degrades to a deterministic fallback (keep the
newest note of the cluster) so sleep can never corrupt memory.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from db.models import Note
from services.ledger import DecisionLedger
from services.logging_utils import get_logger
from services.semantic_index import _cosine, _embed

logger = get_logger(__name__)


class ConsolidationService:
    """Clusters near-duplicate lessons and merges each cluster into one."""

    def __init__(
        self,
        llm_adapter: Any = None,
        *,
        ledger: Optional[DecisionLedger] = None,
        similarity_threshold: float = 0.6,
        dimensions: int = 4096,
    ) -> None:
        self.llm = llm_adapter
        self.ledger = ledger or DecisionLedger()
        self.similarity_threshold = similarity_threshold
        self.dimensions = dimensions

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def consolidate(self, session: Any) -> Dict[str, Any]:
        """Run one consolidation pass. Returns a summary of what merged."""
        notes = (
            session.query(Note)
            .order_by(lambda n: n.created_at)
            .all()
        )
        clusters = self._cluster(notes)
        merge_clusters = [c for c in clusters if len(c) >= 2]
        if not merge_clusters:
            return {"clusters_merged": 0, "notes_removed": 0}

        removed = 0
        for cluster in merge_clusters:
            merged_text = await self._merge_cluster([n.text for n in cluster])
            if not merged_text:
                # Deterministic fallback: the newest note survives.
                merged_text = cluster[-1].text

            for note in cluster:
                session.delete(note)
            session.add(Note(text=merged_text))
            removed += len(cluster) - 1

            self.ledger.record("memory_consolidated", {
                "cluster_size": len(cluster),
                "merged_into": merged_text[:200],
            })

        session.commit()
        logger.info(
            "Dream consolidation merged %d clusters (%d notes removed)",
            len(merge_clusters), removed,
        )
        return {"clusters_merged": len(merge_clusters), "notes_removed": removed}

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _cluster(self, notes: List[Note]) -> List[List[Note]]:
        """Greedy similarity clustering over the notes, oldest first."""
        vectors = [_embed(note.text, self.dimensions) for note in notes]
        clusters: List[List[int]] = []
        assigned: set = set()

        for i in range(len(notes)):
            if i in assigned:
                continue
            cluster = [i]
            assigned.add(i)
            for j in range(i + 1, len(notes)):
                if j in assigned:
                    continue
                if _cosine(vectors[i], vectors[j]) >= self.similarity_threshold:
                    cluster.append(j)
                    assigned.add(j)
            clusters.append(cluster)

        return [[notes[i] for i in cluster] for cluster in clusters]

    async def _merge_cluster(self, texts: List[str]) -> str:
        """Ask the LLM for one sharper lesson; empty string on any failure."""
        if self.llm is None:
            return ""
        system = (
            "You consolidate an autonomous agent's learned lessons. Merge the "
            "given near-duplicate lessons into ONE lesson that keeps every "
            "concrete, actionable detail and drops repetition. Return a single "
            "sentence of at most 45 words. No preamble."
        )
        user_message = "Lessons to merge:\n" + "\n".join(f"- {t}" for t in texts)
        try:
            merged = await self.llm.chat(
                system=system,
                messages=[{"role": "user", "content": user_message}],
                temperature=0.3,
                max_tokens=120,
            )
            merged = (merged or "").strip().strip('"')
            # A merge that lost everything or ballooned is not a merge.
            if not merged or len(merged) > 500:
                return ""
            return merged
        except Exception as exc:
            logger.error(f"Lesson merge failed, using fallback: {exc}")
            return ""


__all__ = ["ConsolidationService"]

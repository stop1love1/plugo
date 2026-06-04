import contextlib
import re

import chromadb

from config import settings

# Words shorter than this are ignored when computing keyword overlap (drops most
# stopwords/articles without needing a stopword list).
_MIN_TERM_LEN = 3
# Maximum additive boost applied to a chunk that contains every query term.
_KEYWORD_BOOST_WEIGHT = 0.15


def _keyword_boost(query_text: str, chunks: list[dict]) -> list[dict]:
    """Hybrid rerank: nudge vector scores up for chunks that literally contain
    query terms, then return a new list re-sorted by the blended score.

    Pure and deterministic — no extra model or dependency — so semantically
    relevant chunks that also share surface terms with the question rise to the
    top, mitigating pure-cosine misses. Input dicts are not mutated (a fresh dict
    with the adjusted score is returned for each), so callers may safely pass
    cached/shared chunk lists.
    """
    terms = {t for t in re.findall(r"\w+", query_text.lower()) if len(t) >= _MIN_TERM_LEN}
    if not terms:
        return chunks
    boosted = []
    for c in chunks:
        content = (c.get("content") or "").lower()
        hits = sum(1 for t in terms if t in content)
        overlap = hits / len(terms)
        boosted.append({**c, "score": min(1.0, c.get("score", 0.0) + _KEYWORD_BOOST_WEIGHT * overlap)})
    return sorted(boosted, key=lambda c: c.get("score", 0.0), reverse=True)


class RAGEngine:
    """Vector search engine using ChromaDB."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy-initialize ChromaDB client on first use."""
        if self._client is None:
            self._client = chromadb.PersistentClient(path=settings.chroma_path)
        return self._client

    def get_collection(self, site_id: str) -> chromadb.Collection:
        return self.client.get_or_create_collection(
            name=f"site_{site_id}",
            metadata={"hnsw:space": "cosine"},
        )

    async def add_chunks(
        self,
        site_id: str,
        chunks: list[dict],
        embeddings: list[list[float]],
    ) -> list[str]:
        """Add document chunks with their embeddings to the vector store."""
        collection = self.get_collection(site_id)
        ids = [chunk["id"] for chunk in chunks]
        documents = [chunk["content"] for chunk in chunks]
        metadatas = [
            {
                "source_url": chunk.get("source_url", ""),
                "title": chunk.get("title", ""),
                "chunk_index": chunk.get("chunk_index", 0),
            }
            for chunk in chunks
        ]

        collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return ids

    async def search(
        self,
        site_id: str,
        query_embedding: list[float],
        top_k: int = 10,
        min_score: float | None = None,
        query_text: str | None = None,
    ) -> list[dict]:
        """Search for the most relevant chunks with optional relevance filtering.

        When ``query_text`` is supplied, survivors are re-ranked with a keyword
        overlap boost (hybrid retrieval) before the max_chunks cap.
        """
        if min_score is None:
            min_score = settings.rag_min_score

        collection = self.get_collection(site_id)

        if collection.count() == 0:
            return []

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        chunks = []
        for i in range(len(results["ids"][0])):
            score = 1 - results["distances"][0][i]  # Convert distance to similarity
            if score < min_score:
                continue
            chunks.append(
                {
                    "id": results["ids"][0][i],
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "score": score,
                }
            )

        # Hybrid rerank on the surviving candidates before capping.
        if query_text:
            chunks = _keyword_boost(query_text, chunks)

        # Cap at max_chunks
        max_chunks = settings.rag_max_chunks
        return chunks[:max_chunks]

    async def delete_chunks(self, site_id: str, chunk_ids: list[str]):
        """Delete specific chunks from vector store."""
        collection = self.get_collection(site_id)
        collection.delete(ids=chunk_ids)

    async def delete_site(self, site_id: str):
        """Delete all data for a site."""
        with contextlib.suppress(ValueError):
            self.client.delete_collection(f"site_{site_id}")  # Collection may not exist


rag_engine = RAGEngine()

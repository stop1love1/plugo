from typing import Optional
import chromadb
from config import settings


class RAGEngine:
    """Vector search engine using ChromaDB."""

    def __init__(self):
        self.client = chromadb.PersistentClient(path=settings.chroma_path)

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
        min_score: Optional[float] = None,
    ) -> list[dict]:
        """Search for the most relevant chunks with optional relevance filtering."""
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
            chunks.append({
                "id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "score": score,
            })

        # Cap at max_chunks
        max_chunks = settings.rag_max_chunks
        return chunks[:max_chunks]

    async def delete_chunks(self, site_id: str, chunk_ids: list[str]):
        """Delete specific chunks from vector store."""
        collection = self.get_collection(site_id)
        collection.delete(ids=chunk_ids)

    async def delete_site(self, site_id: str):
        """Delete all data for a site."""
        try:
            self.client.delete_collection(f"site_{site_id}")
        except ValueError:
            pass  # Collection doesn't exist


rag_engine = RAGEngine()

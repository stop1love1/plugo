"""Thin wrapper around ChromaDB — delegates to agent.rag for actual operations."""

from agent.rag import rag_engine


class VectorStore:
    """High-level interface for vector operations."""

    def __init__(self):
        self.engine = rag_engine

    async def search(self, site_id: str, query_embedding: list[float], top_k: int = 5):
        return await self.engine.search(site_id, query_embedding, top_k)

    async def add(self, site_id: str, chunks: list[dict], embeddings: list[list[float]]):
        return await self.engine.add_chunks(site_id, chunks, embeddings)

    async def delete(self, site_id: str, chunk_ids: list[str]):
        return await self.engine.delete_chunks(site_id, chunk_ids)

    async def delete_site(self, site_id: str):
        return await self.engine.delete_site(site_id)


vector_store = VectorStore()

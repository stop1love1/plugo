import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text

from database import Base


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id = Column(String, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)

    source_url = Column(String(2048), nullable=True)
    source_type = Column(String(50), default="crawl")  # crawl | upload | manual
    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)
    # Composite index below covers (site_id, content_hash) — a standalone index
    # on content_hash is redundant for our access patterns, so drop it.
    content_hash = Column(String(64), nullable=True)

    # Reference to ChromaDB
    embedding_id = Column(String(255), nullable=True)

    crawled_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Composite indexes for the hot paths:
    #   list_crawled_urls / list_by_url  → (site_id, source_url)
    #   create_many dedup / list_content_hashes → (site_id, content_hash)
    __table_args__ = (
        Index("ix_knowledge_chunks_site_url", "site_id", "source_url"),
        Index("ix_knowledge_chunks_site_hash", "site_id", "content_hash"),
    )

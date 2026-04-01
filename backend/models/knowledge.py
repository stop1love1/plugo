import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

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
    content_hash = Column(String(64), nullable=True, index=True)

    # Reference to ChromaDB
    embedding_id = Column(String(255), nullable=True)

    crawled_at = Column(DateTime, default=lambda: datetime.now(UTC))

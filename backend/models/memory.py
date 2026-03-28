import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, Index
from database import Base


class VisitorMemory(Base):
    __tablename__ = "visitor_memories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    visitor_id = Column(String(255), nullable=False, index=True)
    site_id = Column(String, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)

    category = Column(String(50), nullable=False)  # identity, preference, issue, context
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)
    confidence = Column(String(20), default="medium")  # high, medium, low

    source_session_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_visitor_memory_lookup", "visitor_id", "site_id", "key"),
    )


class ConversationSummary(Base):
    __tablename__ = "conversation_summaries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, unique=True)
    site_id = Column(String, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)

    summary_text = Column(Text, nullable=False)
    message_count_summarized = Column(Integer, default=0)
    total_message_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

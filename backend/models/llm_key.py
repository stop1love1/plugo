import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, String, Text

from database import Base


class LLMKey(Base):
    __tablename__ = "llm_keys"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider = Column(String(50), unique=True, nullable=False)  # claude, openai, gemini
    api_key = Column(Text, nullable=False)  # encrypted in production
    label = Column(String(255), default="")  # optional label, e.g. "Production key"

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

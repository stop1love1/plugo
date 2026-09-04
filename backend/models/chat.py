import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String

from database import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id = Column(String, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)

    visitor_id = Column(String(255), nullable=True)
    page_url = Column(String(2048), nullable=True)
    # [{role, content, timestamp, feedback?, tool_calls?}] — `feedback` is "up"/"down"
    # (see routers/sessions.py); `tool_calls` is [{name, success}] for tools the agent
    # actually executed on that turn (see routers/analytics.py get_tool_usage).
    messages = Column(JSON, default=list)

    started_at = Column(DateTime, default=lambda: datetime.now(UTC))
    ended_at = Column(DateTime, nullable=True)

    # Token usage tracking (accumulated across all LLM calls in the session)
    tokens_input = Column(Integer, nullable=False, default=0)
    tokens_output = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)

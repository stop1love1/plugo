import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from database import Base


class Flow(Base):
    __tablename__ = "flows"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id = Column(String, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    requires_login = Column(Boolean, default=False)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class FlowStep(Base):
    __tablename__ = "flow_steps"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    flow_id = Column(String, ForeignKey("flows.id", ondelete="CASCADE"), nullable=False, index=True)
    step_order = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, default="")
    url = Column(String(2048), nullable=True)
    screenshot_url = Column(String(2048), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

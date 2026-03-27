import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Boolean, ForeignKey, JSON
from database import Base


class Tool(Base):
    __tablename__ = "tools"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id = Column(String, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    method = Column(String(10), default="GET")  # GET | POST | PUT | DELETE
    url = Column(String(2048), nullable=False)
    params_schema = Column(JSON, default=dict)
    headers = Column(JSON, default=dict)

    # Auth
    auth_type = Column(String(50), nullable=True)  # bearer | api_key | basic | none
    auth_value = Column(String(500), nullable=True)

    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

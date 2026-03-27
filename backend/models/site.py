import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Boolean, Integer
from database import Base


class Site(Base):
    __tablename__ = "sites"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    url = Column(String(2048), nullable=False)
    token = Column(String(64), unique=True, nullable=False, default=lambda: uuid.uuid4().hex)

    # LLM config per site
    llm_provider = Column(String(50), default="claude")
    llm_model = Column(String(100), default="claude-sonnet-4-20250514")

    # Widget customization
    primary_color = Column(String(7), default="#6366f1")
    greeting = Column(Text, default="Xin chào! Tôi có thể giúp gì cho bạn?")
    position = Column(String(20), default="bottom-right")

    # Domain whitelist (comma-separated)
    allowed_domains = Column(Text, default="")

    # --- Crawl management ---
    crawl_enabled = Column(Boolean, default=False)           # Admin toggle: bật/tắt crawl
    crawl_auto_interval = Column(Integer, default=0)         # Auto re-crawl interval (giờ). 0 = không tự động
    crawl_max_pages = Column(Integer, default=50)            # Số trang tối đa mỗi lần crawl
    crawl_status = Column(String(20), default="idle")        # idle | running | paused
    last_crawled_at = Column(DateTime, nullable=True)        # Lần crawl gần nhất
    knowledge_count = Column(Integer, default=0)             # Số chunks đã học được

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

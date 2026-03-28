import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Boolean, Integer, JSON
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
    greeting = Column(Text, default="Hello! How can I help you?")
    position = Column(String(20), default="bottom-right")
    widget_title = Column(String(100), default="")  # Custom header title (empty = default i18n)
    dark_mode = Column(String(10), default="auto")   # "auto" | "light" | "dark"
    show_branding = Column(Boolean, default=True)     # Show "Powered by Plugo" in widget

    # Default suggestions for the widget
    suggestions = Column(JSON, default=list)

    # Domain whitelist (comma-separated)
    allowed_domains = Column(Text, default="")

    # --- Site approval ---
    is_approved = Column(Boolean, default=False)  # Admin must approve before widget works

    # --- Crawl management ---
    crawl_enabled = Column(Boolean, default=False)           # Admin toggle: enable/disable crawl
    crawl_auto_interval = Column(Integer, default=0)         # Auto re-crawl interval (hours). 0 = disabled
    crawl_max_pages = Column(Integer, default=50)            # Max pages per crawl run
    crawl_status = Column(String(20), default="idle")        # idle | running | paused
    last_crawled_at = Column(DateTime, nullable=True)        # Last crawl timestamp
    knowledge_count = Column(Integer, default=0)             # Total knowledge chunks stored

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

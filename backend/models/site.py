import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text

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
    show_branding = Column(Boolean, default=True)     # Legacy field, no longer used
    bot_avatar = Column(String(10), default="")       # Emoji for bot avatar (e.g. "🤖")
    header_subtitle = Column(String(100), default="") # Subtitle under title (empty = "Online")
    input_placeholder = Column(String(200), default="") # Custom placeholder (empty = default i18n)
    auto_open_delay = Column(Integer, default=0)      # Auto open after N seconds (0 = disabled)
    bubble_size = Column(String(10), default="medium") # "small" | "medium" | "large"

    # AI behavior rules
    system_prompt = Column(Text, default="")         # Custom system prompt for the bot
    bot_rules = Column(Text, default="")             # Rules/constraints for the bot (newline-separated)
    response_language = Column(String(10), default="auto")  # "auto" | "vi" | "en" — language for bot responses

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
    crawl_max_depth = Column(Integer, default=0)             # Max link depth from start URL. 0 = unlimited
    crawl_status = Column(String(20), default="idle")        # idle | running | paused
    crawl_exclude_patterns = Column(Text, default="")        # Newline-separated URL patterns to exclude (glob-style)
    last_crawled_at = Column(DateTime, nullable=True)        # Last crawl timestamp
    knowledge_count = Column(Integer, default=0)             # Total knowledge chunks stored

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

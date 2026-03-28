import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey
from database import Base


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id = Column(String, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)

    status = Column(String(20), default="pending")  # pending | running | completed | failed | stopped
    start_url = Column(String(2048), nullable=False)
    pages_found = Column(Integer, default=0)
    pages_done = Column(Integer, default=0)
    pages_skipped = Column(Integer, default=0)
    pages_failed = Column(Integer, default=0)
    chunks_created = Column(Integer, default=0)
    current_url = Column(String(2048), nullable=True)  # URL currently being crawled

    error_log = Column(Text, nullable=True)
    crawl_log = Column(Text, nullable=True)  # JSON array of per-page log entries (ALL entries)

    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)

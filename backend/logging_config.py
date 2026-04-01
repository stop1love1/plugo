"""
Structured logging configuration using loguru.

Usage:
    from logging_config import logger

    logger.info("Processing request", site_id="abc", action="crawl")
    logger.error("Failed to embed", error=str(e), chunk_id="xyz")
"""

import sys

from loguru import logger as _logger

# Remove default handler
_logger.remove()

# Console handler — human-readable for development
_logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
    level="INFO",
    colorize=True,
)

# File handler — JSON for production log aggregation
_logger.add(
    "data/plugo.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    compression="gz",
)

# Export configured logger
logger = _logger

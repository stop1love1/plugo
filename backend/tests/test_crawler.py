"""Tests for the web crawler text extraction and chunking."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bs4 import BeautifulSoup
from urllib.parse import urlparse

from knowledge.crawler import WebCrawler, _canonical_internal_url, _normalize_host


def test_extract_text_removes_nav_footer():
    """Crawler should strip navigation and footer elements."""
    html = """
    <html>
    <body>
        <nav>Navigation links</nav>
        <main><p>Main content here</p></main>
        <footer>Footer content</footer>
    </body>
    </html>
    """
    crawler = WebCrawler()
    soup = BeautifulSoup(html, "html.parser")
    text = crawler._extract_text(soup)

    assert "Main content here" in text
    assert "Navigation links" not in text
    assert "Footer content" not in text


def test_extract_text_from_article():
    """Crawler should extract text from article tags."""
    html = """
    <html><body>
        <article><h1>Title</h1><p>Article body text.</p></article>
    </body></html>
    """
    crawler = WebCrawler()
    soup = BeautifulSoup(html, "html.parser")
    text = crawler._extract_text(soup)

    assert "Title" in text
    assert "Article body text" in text


def test_chunk_text_splits_correctly():
    """Chunker should split long text into multiple chunks."""
    crawler = WebCrawler()
    long_text = "\n\n".join([f"Paragraph {i} with some content." for i in range(50)])

    chunks = crawler._chunk_text(long_text, "Test Page", "https://example.com", "site_1", max_tokens=50)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk["site_id"] == "site_1"
        assert chunk["source_url"] == "https://example.com"
        assert chunk["title"] == "Test Page"
        assert chunk["content"].strip() != ""
        assert "id" in chunk
        assert chunk.get("content_hash") and len(chunk["content_hash"]) == 64


def test_chunk_text_single_short():
    """Short text should produce a single chunk."""
    crawler = WebCrawler()
    chunks = crawler._chunk_text("Short text.", "Page", "https://example.com", "site_1")

    assert len(chunks) == 1
    assert chunks[0]["content"] == "Short text."
    assert chunks[0].get("content_hash") and len(chunks[0]["content_hash"]) == 64


def test_normalize_host_strips_www():
    assert _normalize_host("WWW.Example.COM") == "example.com"
    assert _normalize_host("example.com") == "example.com"
    assert _normalize_host("blog.example.com") == "blog.example.com"


def test_canonical_internal_url_merges_www_with_apex():
    seed = "https://example.com/"
    assert _canonical_internal_url(seed, urlparse("https://www.example.com/about")) == "https://example.com/about"
    assert _canonical_internal_url(seed, urlparse("https://EXAMPLE.COM/pricing")) == "https://example.com/pricing"


def test_canonical_internal_url_rejects_other_domains():
    assert _canonical_internal_url("https://example.com/", urlparse("https://other.org/x")) is None


def test_crawler_stop_signal():
    """Crawler stop() should set the internal flag."""
    crawler = WebCrawler()
    assert crawler._stopped is False

    crawler.stop()
    assert crawler._stopped is True

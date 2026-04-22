"""Tests for the web crawler text extraction and chunking."""

import os
import socket
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from urllib.parse import urlparse

import pytest
from bs4 import BeautifulSoup

from knowledge.crawler import (
    WebCrawler,
    _canonical_internal_url,
    _is_safe_public_url,
    _normalize_host,
)


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


def test_canonical_internal_url_preserves_query_and_params():
    """Distinct query strings must not collapse to one URL (common for pagination and IDs)."""
    seed = "https://example.com/"
    u1 = _canonical_internal_url(seed, urlparse("https://example.com/list?page=2"))
    u2 = _canonical_internal_url(seed, urlparse("https://example.com/list?page=3"))
    assert u1 == "https://example.com/list?page=2"
    assert u2 == "https://example.com/list?page=3"
    assert u1 != u2
    assert _canonical_internal_url(seed, urlparse("https://example.com/doc;type=pdf?id=1")) == (
        "https://example.com/doc;type=pdf?id=1"
    )


def test_canonical_internal_url_strips_fragment():
    assert _canonical_internal_url("https://example.com/", urlparse("https://example.com/docs#section")) == (
        "https://example.com/docs"
    )


def test_crawler_stop_signal():
    """Crawler stop() should set the internal flag."""
    crawler = WebCrawler()
    assert crawler._stopped is False

    crawler.stop()
    assert crawler._stopped is True


@pytest.mark.asyncio
async def test_is_safe_public_url_rejects_unsafe():
    """SSRF guard must reject non-http, loopback, private, link-local, and cloud metadata URLs."""
    # 1. Non-http(s) scheme
    ok, reason = await _is_safe_public_url("file:///etc/passwd")
    assert not ok and "scheme" in reason

    # 2. localhost hostname
    ok, reason = await _is_safe_public_url("http://localhost/secret")
    assert not ok and "localhost" in reason

    # 3. Loopback IP
    ok, reason = await _is_safe_public_url("http://127.0.0.1:8000/admin")
    assert not ok and "127.0.0.1" in reason

    # 4. Private IP
    ok, reason = await _is_safe_public_url("http://192.168.1.1/")
    assert not ok and "192.168.1.1" in reason

    # 5. Cloud metadata endpoint
    ok, reason = await _is_safe_public_url("http://169.254.169.254/latest/meta-data/")
    assert not ok

    # And also metadata.google.internal
    ok, _ = await _is_safe_public_url("http://metadata.google.internal/")
    assert not ok


@pytest.mark.asyncio
async def test_is_safe_public_url_allows_public():
    """Legitimate public URLs must pass the SSRF guard (DNS resolution returns public IPs)."""
    # Mock DNS so the test doesn't depend on live name resolution.
    public_info = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]
    with patch("knowledge.crawler.socket.getaddrinfo", return_value=public_info):
        ok, _ = await _is_safe_public_url("https://example.com/page")
        assert ok
    # IP literal path doesn't hit DNS
    ok, _ = await _is_safe_public_url("http://8.8.8.8/")
    assert ok


@pytest.mark.asyncio
async def test_is_safe_public_url_rejects_dns_resolving_to_private():
    """DNS rebinding defense: reject when a public hostname resolves to a private IP."""
    # Simulate evil.com resolving to a private/internal address.
    private_info = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("169.254.169.254", 0))]
    with patch("knowledge.crawler.socket.getaddrinfo", return_value=private_info):
        ok, reason = await _is_safe_public_url("https://evil.example.com/path")
    assert not ok
    assert "169.254.169.254" in reason or "internal" in reason.lower()

    # Also test a classic RFC1918 private address.
    rfc1918_info = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 0))]
    with patch("knowledge.crawler.socket.getaddrinfo", return_value=rfc1918_info):
        ok, reason = await _is_safe_public_url("https://rebind.example.com/")
    assert not ok
    assert "10.0.0.1" in reason or "internal" in reason.lower()


@pytest.mark.asyncio
async def test_is_safe_public_url_rejects_dns_resolution_failure():
    """Conservative default: if DNS resolution fails, reject the URL."""
    with patch(
        "knowledge.crawler.socket.getaddrinfo",
        side_effect=socket.gaierror("name or service not known"),
    ):
        ok, reason = await _is_safe_public_url("https://nonexistent.invalid/")
    assert not ok
    assert "DNS" in reason or "resolution" in reason.lower()


@pytest.mark.asyncio
async def test_is_safe_public_url_allow_private_flag():
    """With allow_private=True, localhost and RFC1918 IPs are permitted — but cloud
    metadata endpoints MUST still be blocked (credential-exfil risk)."""
    # Localhost literal passes when flag is set.
    ok, _ = await _is_safe_public_url("http://localhost:9999/login", allow_private=True)
    assert ok
    # Loopback IP passes.
    ok, _ = await _is_safe_public_url("http://127.0.0.1:8000/", allow_private=True)
    assert ok
    # RFC1918 IP passes.
    ok, _ = await _is_safe_public_url("http://192.168.1.1/", allow_private=True)
    assert ok
    # Cloud metadata NEVER passes, even with the flag.
    ok, reason = await _is_safe_public_url("http://169.254.169.254/latest/", allow_private=True)
    assert not ok and "metadata" in reason.lower()
    ok, _ = await _is_safe_public_url("http://metadata.google.internal/", allow_private=True)
    assert not ok
    # DNS resolving to private IP passes with flag (on-prem wiki behind reverse proxy).
    private_info = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.5", 0))]
    with patch("knowledge.crawler.socket.getaddrinfo", return_value=private_info):
        ok, _ = await _is_safe_public_url("https://wiki.internal/", allow_private=True)
    assert ok

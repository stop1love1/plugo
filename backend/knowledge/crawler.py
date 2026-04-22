import asyncio
import fnmatch
import hashlib
import ipaddress
import json
import os
import re
import socket
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import ParseResult, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from agent.rag import rag_engine
from config import settings
from knowledge.chunker import SemanticChunker
from logging_config import logger
from providers.factory import get_llm_provider

# Hostnames used by cloud metadata services — always block to avoid credential exfil via SSRF.
_BLOCKED_METADATA_HOSTS = frozenset({
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.azure.com",
})
_BLOCKED_LITERAL_HOSTS = frozenset({"localhost", "0.0.0.0", "::1"})


def _ip_is_unsafe(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the IP address is not publicly routable."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def _is_safe_public_url(url: str, allow_private: bool = False) -> tuple[bool, str]:
    """Return (is_safe, reason). Reject non-http(s), loopback, private, link-local,
    reserved IPs, and well-known cloud metadata endpoints to prevent SSRF.

    DNS rebinding defense: if the host is a name, resolve it via getaddrinfo and
    reject if ANY resolved IP is private/loopback/etc. DNS resolution failures are
    treated as unsafe (conservative default).

    If `allow_private=True`, loopback/private/link-local IPs are permitted but cloud
    metadata endpoints are STILL blocked (credential-exfil risk remains).
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"invalid URL: {e}"
    if parsed.scheme not in ("http", "https"):
        return False, f"unsupported scheme: {parsed.scheme or '(none)'}"
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "missing hostname"
    if hostname in _BLOCKED_METADATA_HOSTS:
        return False, f"blocked cloud metadata endpoint: {hostname}"
    if not allow_private and hostname in _BLOCKED_LITERAL_HOSTS:
        return False, f"blocked host: {hostname}"
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        # Hostname is not an IP literal — resolve via DNS and check every answer.
        try:
            infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
        except socket.gaierror as e:
            return False, f"DNS resolution failed for {hostname}: {e}"
        except Exception as e:
            return False, f"DNS resolution error for {hostname}: {e}"
        if not infos:
            return False, f"DNS returned no addresses for {hostname}"
        for info in infos:
            sockaddr = info[4]
            addr_str = sockaddr[0] if sockaddr else None
            if not addr_str:
                continue
            # Strip IPv6 scope-id if present (e.g. "fe80::1%eth0")
            if "%" in addr_str:
                addr_str = addr_str.split("%", 1)[0]
            try:
                resolved = ipaddress.ip_address(addr_str)
            except ValueError:
                return False, f"DNS returned non-IP address for {hostname}: {addr_str}"
            if not allow_private and _ip_is_unsafe(resolved):
                return False, f"blocked internal IP via DNS ({hostname} -> {addr_str})"
        return True, ""
    if not allow_private and _ip_is_unsafe(ip):
        return False, f"blocked internal IP: {hostname}"
    return True, ""


def _normalize_host(netloc: str) -> str:
    """Lowercase host and strip a leading www. so apex and www are treated as one site."""
    if not netloc:
        return ""
    h = netloc.lower().strip()
    if h.startswith("www."):
        h = h[4:]
    return h


def _canonical_internal_url(start_url: str, parsed: ParseResult) -> str | None:
    """If parsed URL is on the same site as start_url (www-agnostic), return a stable URL using the seed host.

    Preserves path, params, and query so distinct pages (e.g. ?page=2, ?id=1) are not collapsed.
    Fragment is omitted: it is not sent to the server and would incorrectly dedupe different HTML fetches.
    """
    seed = urlparse(start_url)
    if _normalize_host(parsed.netloc) != _normalize_host(seed.netloc):
        return None
    scheme = parsed.scheme if parsed.scheme in ("http", "https") else seed.scheme
    if scheme not in ("http", "https"):
        scheme = seed.scheme if seed.scheme in ("http", "https") else "https"
    path = parsed.path if parsed.path else "/"
    params = f";{parsed.params}" if parsed.params else ""
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{scheme}://{seed.netloc.lower()}{path}{params}{query}"


class WebCrawler:
    """Crawls websites, extracts text, chunks, and embeds content.

    Supports graceful stop and pause: when an admin stops/pauses the crawl,
    the crawler halts but persists all data collected so far to the database.
    """

    def __init__(
        self,
        max_pages: int = 50,
        delay: float | None = None,
        force_recrawl: bool = False,
        max_depth: int = 0,
        exclude_patterns: list[str] | None = None,
        auth_cookies: list[dict] | None = None,
        login_url: str | None = None,
        allow_private_urls: bool = False,
    ):
        self.max_pages = max_pages
        self.delay = delay if delay is not None else settings.crawl_request_delay
        self.allow_private_urls = allow_private_urls
        self.visited: set[str] = set()
        self._stopped = False
        self._paused = False
        self.chunker = SemanticChunker()
        self.logs: list[dict] = []
        self.pages_skipped = 0
        self.pages_failed = 0
        self.pages_retried = 0
        self.chunks_created = 0
        self.current_url: str | None = None
        self.force_recrawl = force_recrawl
        self._already_crawled_urls: set[str] = set()
        self._page_hashes: dict[str, str] = {}
        self._queue_size = 0
        self.max_depth = 0 if max_depth is None else int(max_depth)  # 0 = unlimited
        self.exclude_patterns = exclude_patterns or []
        self.max_retries = settings.crawl_max_retries
        self.auth_cookies = auth_cookies
        self.login_url = login_url
        self._consecutive_auth_failures = 0

    def stop(self):
        """Signal the crawler to stop. Data already crawled will be persisted."""
        self._stopped = True

    def pause(self):
        """Signal the crawler to pause."""
        self._paused = True

    def resume(self):
        """Resume a paused crawler."""
        self._paused = False

    def _log(self, url: str, status: str, title: str = "", chunks: int = 0, error: str | None = None, action: str = ""):
        entry = {
            "url": url,
            "status": status,
            "title": title,
            "chunks": chunks,
            "error": error,
            "action": action,
            "page_number": len(self.visited),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.logs.append(entry)
        # Cap logs to prevent unbounded growth on large crawls
        if len(self.logs) > 500:
            self.logs.pop(0)
        if status == "error":
            logger.warning("Crawl page error", url=url, error=error)
        return entry

    def _is_excluded(self, url: str) -> bool:
        """Check if a URL matches any exclude pattern."""
        for pattern in self.exclude_patterns:
            pattern = pattern.strip()
            if not pattern:
                continue
            # Support glob-style patterns
            if fnmatch.fnmatch(url, pattern):
                return True
            # Also check if pattern is a substring (e.g. "/admin/")
            if pattern in url:
                return True
        return False

    async def _check_robots_txt(self, client: httpx.AsyncClient, start_url: str) -> RobotFileParser:
        parsed = urlparse(start_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        try:
            response = await client.get(robots_url)
            if response.status_code == 200:
                rp.parse(response.text.splitlines())
                self._log(robots_url, "success", action="robots.txt parsed")
            else:
                rp.parse([])
                self._log(robots_url, "skipped", action="robots.txt not found, allowing all")
        except Exception as e:
            rp.parse([])
            self._log(robots_url, "skipped", error=str(e), action="robots.txt fetch failed, allowing all")
        return rp

    async def _parse_sitemap(self, client: httpx.AsyncClient, start_url: str) -> list[str]:
        """Try to discover URLs from sitemap.xml."""
        parsed = urlparse(start_url)
        seed_host_norm = _normalize_host(parsed.netloc)
        sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
        urls = []
        try:
            response = await client.get(sitemap_url)
            if response.status_code != 200:
                self._log(sitemap_url, "skipped", action="sitemap.xml not found or not XML")
            else:
                raw = response.text.strip()
                ct = (response.headers.get("content-type") or "").lower()
                head = raw[:8000].lower()
                looks_like_sitemap = (
                    "xml" in ct
                    or raw.startswith("<?xml")
                    or "<urlset" in head
                    or "<sitemapindex" in head
                )
                if not looks_like_sitemap:
                    self._log(sitemap_url, "skipped", action="sitemap.xml response not recognized as XML")
                else:
                    soup = BeautifulSoup(response.text, "html.parser")
                    for loc in soup.find_all("loc"):
                        url = loc.get_text(strip=True)
                        url_parsed = urlparse(url)
                        if _normalize_host(url_parsed.netloc) != seed_host_norm:
                            continue
                        clean_url = _canonical_internal_url(start_url, url_parsed)
                        if clean_url and not self._is_excluded(clean_url):
                            urls.append(clean_url)
                    if urls:
                        self._log(sitemap_url, "success", action=f"sitemap.xml: discovered {len(urls)} URLs")
                    else:
                        self._log(sitemap_url, "skipped", action="sitemap.xml parsed but no usable URLs found")
        except Exception as e:
            self._log(sitemap_url, "skipped", error=str(e), action="sitemap.xml fetch failed")
        return urls

    async def _save_progress(self, job_id: str, repos):
        await repos.crawl_jobs.update(job_id, {
            "pages_found": len(self.visited) + self._queue_size,
            "pages_done": len(self.visited),
            "pages_skipped": self.pages_skipped,
            "pages_failed": self.pages_failed,
            "chunks_created": self.chunks_created,
            "current_url": self.current_url,
            "crawl_log": json.dumps(self.logs),
        })

    def _compute_page_hash(self, html: str) -> str:
        normalized = re.sub(r"\s+", " ", html).strip()
        return hashlib.sha256(normalized.encode()).hexdigest()

    async def _flush_chunks(self, site_id: str, chunks: list[dict], repos):
        if not chunks:
            return
        self._log("", "success", action=f"embedding batch of {len(chunks)} chunks...")
        await self._embed_and_store(site_id, chunks, repos)
        self._log("", "success", action=f"stored batch of {len(chunks)} chunks")

    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> tuple[int | None, str | None, str | None]:
        """Fetch a URL with retry logic. Returns (status_code, content_type, html).
        status_code: None=timeout, -1=error (html contains error message).
        Also detects redirect-to-login as a 401 auth failure.

        Redirects are handled manually (httpx client has follow_redirects=False) so
        each hop can be re-validated against the SSRF guard."""
        safe, reason = await _is_safe_public_url(url, allow_private=self.allow_private_urls)
        if not safe:
            return (-1, None, f"blocked: internal URL ({reason})")
        last_error = None
        for attempt in range(1 + self.max_retries):
            try:
                current_url = url
                response = None
                for _hop in range(5):  # max 5 redirect hops
                    response = await client.get(current_url)
                    if response.status_code not in (301, 302, 303, 307, 308):
                        break
                    location = response.headers.get("location")
                    if not location:
                        break
                    next_url = urljoin(current_url, location)
                    safe, reason = await _is_safe_public_url(next_url, allow_private=self.allow_private_urls)
                    if not safe:
                        return (-1, None, f"blocked redirect to internal URL ({reason})")
                    current_url = next_url
                else:
                    # Too many redirects
                    return (-1, None, "too many redirects (>5)")

                if response is None:
                    return (-1, None, "no response")

                # Detect redirect to login URL (session expired) — compare final URL
                if self.login_url and response.status_code == 200:
                    final_url = current_url
                    if self.login_url in final_url and final_url != url:
                        logger.warning(
                            "Session may have expired — redirected to login page",
                            url=url,
                            redirected_to=final_url,
                        )
                        # Return 401 to trigger auth failure handling
                        return (401, response.headers.get("content-type", ""), response.text)
                return (response.status_code, response.headers.get("content-type", ""), response.text)
            except httpx.TimeoutException:
                last_error = "timeout"
                if attempt < self.max_retries:
                    self.pages_retried += 1
                    self._log(url, "skipped", action=f"timeout, retrying ({attempt + 1}/{self.max_retries})...")
                    await asyncio.sleep(self.delay * (attempt + 1))
            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    self.pages_retried += 1
                    self._log(url, "skipped", action=f"error, retrying ({attempt + 1}/{self.max_retries})...")
                    await asyncio.sleep(self.delay * (attempt + 1))

        if last_error == "timeout":
            return (None, None, None)
        return (-1, None, last_error)

    def _get_temp_dir(self, site_id: str) -> Path:
        """Get or create the temp directory for raw crawl data."""
        temp_dir = Path("data/temp") / site_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    def _cleanup_temp(self, site_id: str):
        """Delete temp files after knowledge has been stored."""
        import shutil
        temp_dir = Path("data/temp") / site_id
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                self._log("", "success", action=f"cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.warning("Failed to clean up temp directory", path=str(temp_dir), error=str(e))

    def _save_raw_page(self, site_id: str, url: str, html: str, title: str, soup: BeautifulSoup) -> Path:
        """Save full page content as markdown with media links to temp directory."""
        temp_dir = self._get_temp_dir(site_id)
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        safe_name = re.sub(r"[^\w\-]", "_", urlparse(url).path.strip("/"))[:60] or "index"
        filename = f"{safe_name}_{url_hash}.md"
        filepath = temp_dir / filename

        # --- Extract main text content as markdown ---
        # Work on a copy so we don't mutate the original soup
        page_soup = BeautifulSoup(str(soup), "html.parser")
        for tag in page_soup.find_all(["script", "style"]):
            tag.decompose()
        main = page_soup.find("main") or page_soup.find("article") or page_soup.find("body")
        body_parts: list[str] = []
        if main:
            for el in main.descendants:
                if not hasattr(el, "name"):
                    continue
                if el.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    level = int(el.name[1])
                    text = el.get_text(strip=True)
                    if text:
                        body_parts.append(f"\n{'#' * level} {text}\n")
                elif el.name == "p":
                    text = el.get_text(strip=True)
                    if text and len(text) > 5:
                        body_parts.append(text)
                elif el.name == "li":
                    text = el.get_text(strip=True)
                    if text:
                        body_parts.append(f"- {text}")
                elif el.name == "blockquote":
                    text = el.get_text(strip=True)
                    if text:
                        body_parts.append(f"> {text}")

        # --- Extract media links ---
        images = []
        videos = []
        file_links = []
        for img in soup.find_all("img"):
            # Prefer lazy-load attributes over src (which is often a placeholder data: URI)
            src = img.get("data-src") or img.get("data-lazy-src") or img.get("data-original") or img.get("src") or ""
            if not src or src.startswith("data:"):
                continue
            src = urljoin(url, src)
            alt = img.get("alt", "").strip()
            if src.startswith(("http://", "https://")):
                images.append({"src": src, "alt": alt})
        for vid in soup.find_all(["video", "iframe"]):
            src = vid.get("src") or ""
            if not src:
                source_tag = vid.find("source", src=True)
                if source_tag:
                    src = source_tag["src"]
            if src:
                src = urljoin(url, src)
                if src.startswith(("http://", "https://")):
                    videos.append(src)
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            text = a.get_text(strip=True)
            ext = os.path.splitext(urlparse(href).path)[1].lower()
            if ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rar"):
                file_links.append({"href": href, "text": text, "type": ext})

        # --- Build markdown file ---
        md_parts = [f"# {title}\n", f"**URL:** {url}\n"]

        # Page content
        if body_parts:
            md_parts.append("\n## Content\n")
            md_parts.append("\n\n".join(body_parts))

        if images:
            md_parts.append("\n\n## Images\n")
            for img in images:
                alt = img["alt"] or "image"
                md_parts.append(f"![{alt}]({img['src']})")

        if videos:
            md_parts.append("\n\n## Videos\n")
            for v in videos:
                md_parts.append(f"- [Video]({v})")

        if file_links:
            md_parts.append("\n\n## Downloadable Files\n")
            for lnk in file_links:
                md_parts.append(f"- [{lnk['text'] or lnk['type']}]({lnk['href']})")

        filepath.write_text("\n".join(md_parts), encoding="utf-8")
        return filepath

    async def crawl_site(
        self,
        site_id: str,
        start_url: str,
        job_id: str,
        repos,
    ):
        """Crawl a website starting from the given URL."""
        p0 = urlparse(start_url)
        _seed_path = p0.path if p0.path else "/"
        _seed_params = f";{p0.params}" if p0.params else ""
        _seed_q = f"?{p0.query}" if p0.query else ""
        start_url = f"{p0.scheme}://{p0.netloc.lower()}{_seed_path}{_seed_params}{_seed_q}"

        # SSRF guard — reject internal/loopback/private/metadata URLs before any network I/O.
        # Cloud-metadata endpoints are always blocked; private/loopback may be allowed per-site.
        safe, reason = await _is_safe_public_url(start_url, allow_private=self.allow_private_urls)
        if not safe:
            self._log(start_url, "error", error=reason, action="blocked unsafe start URL")
            await repos.crawl_jobs.update(job_id, {
                "status": "failed",
                "error_log": f"Refused to crawl unsafe URL: {reason}",
                "crawl_log": json.dumps(self.logs),
                "current_url": None,
                "finished_at": datetime.now(UTC),
            })
            return

        base_domain = urlparse(start_url).netloc
        # Queue stores (url, depth) tuples
        queue: deque[tuple[str, int]] = deque([(start_url, 0)])
        queued_urls: set[str] = {start_url}
        self._queue_size = len(queue)
        pending_chunks: list[dict] = []
        embed_batch_size = settings.crawl_embed_batch_size
        # Background embedding tasks run in parallel with crawling
        embed_tasks: list[asyncio.Task] = []
        # Track content hashes seen in this crawl to avoid duplicate chunks
        seen_hashes: set[str] = set()

        await repos.crawl_jobs.update(job_id, {
            "status": "running",
            "current_url": start_url,
        })

        # Load already-crawled URLs and hashes for change detection and dedup
        if not self.force_recrawl:
            existing_urls = await repos.knowledge.list_crawled_urls(site_id)
            self._already_crawled_urls = {u["source_url"] for u in existing_urls if u.get("source_url")}
            if self._already_crawled_urls:
                self._log("", "success", action=f"found {len(self._already_crawled_urls)} previously crawled URLs")
            # Pre-load existing content hashes to skip duplicates
            existing_hashes = await repos.knowledge.list_content_hashes(site_id)
            seen_hashes.update(existing_hashes)
            if existing_hashes:
                self._log("", "success", action=f"loaded {len(existing_hashes)} existing content hashes for dedup")

        features = []
        if self.max_depth > 0:
            features.append(f"depth≤{self.max_depth}")
        if self.exclude_patterns:
            features.append(f"{len(self.exclude_patterns)} exclude patterns")
        if self.force_recrawl:
            features.append("force-recrawl")
        feature_str = f" [{', '.join(features)}]" if features else ""
        self._log(start_url, "success", action=f"crawl started — target: {base_domain}, max {self.max_pages} pages{feature_str}")

        try:
            client_kwargs = {
                "timeout": settings.crawl_request_timeout,
                # Redirects are handled manually in _fetch_with_retry so each hop is
                # re-validated against the SSRF guard (public URL -> private IP bypass).
                "follow_redirects": False,
                "verify": settings.crawl_verify_ssl,
                "headers": {"User-Agent": "PlugoBot/1.0 (+https://github.com/stop1love1/plugo)"},
            }
            if self.auth_cookies:
                # Use simple dict for cookies — httpx.Cookies with domain can fail for localhost/IP
                cookie_dict = {c["name"]: c["value"] for c in self.auth_cookies}
                client_kwargs["cookies"] = cookie_dict
                domains = list({c.get("domain", "") for c in self.auth_cookies})
                self._log("", "success", action=f"using {len(self.auth_cookies)} auth cookies for authenticated crawl (domains: {domains})")

            async with httpx.AsyncClient(**client_kwargs) as client:
                robot_parser = await self._check_robots_txt(client, start_url)

                # Seed queue from sitemap.xml
                sitemap_urls = await self._parse_sitemap(client, start_url)
                for surl in sitemap_urls:
                    if surl not in queued_urls:
                        queue.append((surl, 1))
                        queued_urls.add(surl)
                self._queue_size = len(queue)

                while queue and len(self.visited) < self.max_pages:
                    # Check stop signal
                    if self._stopped:
                        self._log("", "success", action="crawl stopped by user")
                        break

                    # Check pause signal — wait until resumed
                    while self._paused and not self._stopped:
                        await asyncio.sleep(1)
                    if self._stopped:
                        self._log("", "success", action="crawl stopped while paused")
                        break

                    url, depth = queue.popleft()
                    self._queue_size = len(queue)
                    if url in self.visited:
                        continue

                    # Check robots.txt
                    if not robot_parser.can_fetch("PlugoBot/1.0", url):
                        self._log(url, "skipped", action="blocked by robots.txt")
                        self.pages_skipped += 1
                        continue

                    # Check exclude patterns
                    if self._is_excluded(url):
                        self._log(url, "skipped", action="matched exclude pattern")
                        self.pages_skipped += 1
                        continue

                    self.current_url = url
                    is_recrawl = url in self._already_crawled_urls

                    try:
                        status_code, content_type, html = await self._fetch_with_retry(client, url)

                        if status_code is None:
                            self._log(url, "error", error="Request timed out (all retries exhausted)", action=f"timeout after {settings.crawl_request_timeout}s")
                            self.pages_failed += 1
                            await self._save_progress(job_id, repos)
                            continue

                        if status_code == -1:
                            self._log(url, "error", error=html, action="fetch failed (all retries exhausted)")
                            self.pages_failed += 1
                            await self._save_progress(job_id, repos)
                            continue

                        # Detect auth failures: 401, 403, or redirect to login URL
                        # (redirect-to-login is detected in _fetch_with_retry and returned as 401)
                        is_auth_failure = status_code in (401, 403)

                        if is_auth_failure:
                            self._consecutive_auth_failures += 1
                            logger.warning(
                                "Session may have expired",
                                status=status_code,
                                url=url,
                                consecutive_failures=self._consecutive_auth_failures,
                            )
                            if self._consecutive_auth_failures > 3:
                                logger.error(
                                    "Too many consecutive auth failures — stopping crawl",
                                    consecutive_failures=self._consecutive_auth_failures,
                                )
                                self._log(url, "error", error=f"HTTP {status_code}", action="session expired — too many consecutive auth failures, stopping crawl")
                                self.pages_failed += 1
                                await self._save_progress(job_id, repos)
                                self._stopped = True
                                break
                            self._log(url, "skipped", error=f"HTTP {status_code}", action=f"possible auth failure ({self._consecutive_auth_failures}/3 before stop)")
                            self.pages_skipped += 1
                            await self._save_progress(job_id, repos)
                            continue

                        if status_code != 200:
                            # Reset consecutive auth failure counter on non-auth errors
                            self._consecutive_auth_failures = 0
                            self._log(url, "skipped", error=f"HTTP {status_code}", action="non-200 response")
                            self.pages_skipped += 1
                            await self._save_progress(job_id, repos)
                            continue

                        # Successful page — reset consecutive auth failure counter
                        self._consecutive_auth_failures = 0

                        if "text/html" not in (content_type or ""):
                            self._log(url, "skipped", action=f"non-HTML content: {(content_type or '').split(';')[0]}")
                            self.pages_skipped += 1
                            continue

                        self.visited.add(url)

                        # Change detection: skip if page content hasn't changed
                        page_hash = self._compute_page_hash(html)
                        if is_recrawl and not self.force_recrawl:
                            old_hash = self._page_hashes.get(url)
                            if old_hash and old_hash == page_hash:
                                self._log(url, "skipped", action="content unchanged since last crawl")
                                self.pages_skipped += 1
                                continue
                        self._page_hashes[url] = page_hash

                        soup = BeautifulSoup(html, "html.parser")
                        title = (soup.title.string or "").strip() if soup.title else ""

                        # Save raw page data (with media links) to temp BEFORE soup mutation
                        try:
                            self._save_raw_page(site_id, url, html, title, soup)
                        except Exception as e:
                            logger.warning("Failed to save raw page to temp", url=url, error=str(e))

                        # Discover links BEFORE chunking/text extraction mutates the soup
                        child_depth = depth + 1
                        if self.max_depth == 0 or child_depth <= self.max_depth:
                            for link in soup.find_all(["a", "area"], href=True):
                                href = urljoin(url, link["href"])
                                parsed = urlparse(href)
                                clean_url = _canonical_internal_url(start_url, parsed)
                                if (
                                    clean_url
                                    and clean_url not in self.visited
                                    and clean_url not in queued_urls
                                    and not self._is_excluded(clean_url)
                                ):
                                    safe, _ = await _is_safe_public_url(clean_url, allow_private=self.allow_private_urls)
                                    if safe:
                                        queue.append((clean_url, child_depth))
                                        queued_urls.add(clean_url)

                        # Extract media links in markdown format before soup mutation
                        media_md = self._extract_media_markdown(soup, url)

                        chunks = self.chunker.chunk_page(soup, title, url, site_id)
                        if not chunks:
                            text = self._extract_text(soup)
                            if text.strip():
                                chunks = self._chunk_text(text, title, url, site_id)

                        # Append media markdown to the last chunk (or create one)
                        if media_md:
                            if chunks:
                                chunks[-1]["content"] += "\n\n" + media_md
                                chunks[-1]["content_hash"] = hashlib.sha256(chunks[-1]["content"].encode()).hexdigest()
                            else:
                                chunks = [{
                                    "id": str(uuid.uuid4()),
                                    "site_id": site_id,
                                    "source_url": url,
                                    "title": title,
                                    "content": media_md,
                                    "chunk_index": 0,
                                    "content_hash": hashlib.sha256(media_md.encode()).hexdigest(),
                                }]

                        # Deduplicate: skip chunks with hashes already seen in this crawl
                        unique_chunks = []
                        for c in chunks:
                            h = c.get("content_hash", "")
                            if h and h in seen_hashes:
                                continue
                            if h:
                                seen_hashes.add(h)
                            unique_chunks.append(c)
                        pending_chunks.extend(unique_chunks)
                        self.chunks_created += len(unique_chunks)

                        recrawl_tag = " (re-crawl)" if is_recrawl else ""
                        depth_tag = f" [depth={depth}]" if self.max_depth > 0 else ""
                        self._log(
                            url, "success",
                            title=title,
                            chunks=len(chunks),
                            action=f"extracted {len(chunks)} chunks ({len(html)} bytes){recrawl_tag}{depth_tag}",
                        )

                        self._queue_size = len(queue)

                        # Save progress BEFORE embedding so the UI stays updated
                        await self._save_progress(job_id, repos)

                        # Flush chunks in background so crawling continues in parallel
                        if len(pending_chunks) >= embed_batch_size:
                            batch = list(pending_chunks)
                            pending_chunks.clear()
                            task = asyncio.create_task(self._flush_chunks(site_id, batch, repos))
                            embed_tasks.append(task)

                        await asyncio.sleep(self.delay)

                    except Exception as e:
                        self._log(url, "error", error=str(e), action="unexpected error")
                        self.pages_failed += 1
                        job = await repos.crawl_jobs.get_by_id(job_id)
                        error_log = (job.get("error_log") or "") + f"\n{url}: {e!s}"
                        await repos.crawl_jobs.update(job_id, {"error_log": error_log})
                        await self._save_progress(job_id, repos)
                        continue

            # Wait for any background embedding tasks
            if embed_tasks:
                self._log("", "success", action=f"waiting for {len(embed_tasks)} background embedding tasks...")
                await asyncio.gather(*embed_tasks, return_exceptions=True)
                embed_tasks.clear()

            # Flush remaining chunks
            if pending_chunks:
                await self._flush_chunks(site_id, pending_chunks, repos)
                pending_chunks.clear()

            # Clean up temp files after all knowledge is stored
            self._cleanup_temp(site_id)

            final_status = "paused" if self._paused else ("stopped" if self._stopped else "completed")
            retried_str = f", {self.pages_retried} retried" if self.pages_retried > 0 else ""
            summary = (
                f"Crawl {final_status}: {len(self.visited)} pages crawled, "
                f"{self.pages_skipped} skipped, {self.pages_failed} failed{retried_str}, "
                f"{self.chunks_created} chunks created"
            )
            self._log("", "success", action=summary)

            await repos.crawl_jobs.update(job_id, {
                "status": final_status,
                "pages_done": len(self.visited),
                "pages_skipped": self.pages_skipped,
                "pages_failed": self.pages_failed,
                "chunks_created": self.chunks_created,
                "current_url": None,
                "crawl_log": json.dumps(self.logs),
                "finished_at": datetime.now(UTC),
            })

        except Exception as e:
            # Wait for any in-flight background embedding tasks
            if embed_tasks:
                await asyncio.gather(*embed_tasks, return_exceptions=True)
            if pending_chunks:
                try:
                    await self._flush_chunks(site_id, pending_chunks, repos)
                except Exception:
                    logger.error("Failed to flush chunks on error", site_id=site_id)

            self._log("", "error", error=str(e), action="crawl failed with fatal error")
            await repos.crawl_jobs.update(job_id, {
                "status": "failed",
                "error_log": str(e),
                "crawl_log": json.dumps(self.logs),
                "current_url": None,
                "finished_at": datetime.now(UTC),
            })

    # Structural tags that must never be decomposed by the class-name filter
    _PROTECTED_TAGS = frozenset({"html", "body", "main", "article", "section"})

    def _extract_media_markdown(self, soup: BeautifulSoup, base_url: str) -> str:
        """Extract images, videos, and downloadable file links as markdown."""
        parts = []
        main = soup.find("main") or soup.find("article") or soup.find("body")
        if not main:
            return ""

        # Images (including lazy-loaded — check data-src first since src is often a placeholder)
        images_seen = set()
        for img in main.find_all("img"):
            src = img.get("data-src") or img.get("data-lazy-src") or img.get("data-original") or img.get("src") or ""
            if not src or src.startswith("data:"):
                continue
            src = urljoin(base_url, src)
            if not src.startswith(("http://", "https://")) or src in images_seen:
                continue
            # Skip tiny icons/trackers
            try:
                w = img.get("width", "")
                h = img.get("height", "")
                if (w and int(w) < 20) or (h and int(h) < 20):
                    continue
            except (ValueError, TypeError):
                pass
            images_seen.add(src)
            alt = img.get("alt", "").strip() or "image"
            parts.append(f"![{alt}]({src})")

        # Videos (video tags and iframes like YouTube)
        for vid in main.find_all(["video", "iframe"]):
            src = vid.get("src") or ""
            if not src:
                source_tag = vid.find("source", src=True)
                if source_tag:
                    src = source_tag["src"]
            if src:
                src = urljoin(base_url, src)
                if src.startswith(("http://", "https://")):
                    parts.append(f"[Video]({src})")

        # Downloadable files
        for a in main.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            ext = os.path.splitext(urlparse(href).path)[1].lower()
            if ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rar", ".csv"):
                text = a.get_text(strip=True) or f"File ({ext})"
                parts.append(f"[{text}]({href})")

        return "\n".join(parts)

    def _extract_text(self, soup: BeautifulSoup) -> str:
        for tag in soup.find_all(["nav", "footer", "header", "script", "style", "aside"]):
            tag.decompose()
        for el in soup.find_all(class_=re.compile(r"(nav|footer|sidebar|ad|menu|cookie)", re.I)):
            if el.name not in self._PROTECTED_TAGS:
                el.decompose()

        main = soup.find("main") or soup.find("article") or soup.find("body")
        if not main:
            return ""

        text = main.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _chunk_text(
        self,
        text: str,
        title: str,
        source_url: str,
        site_id: str,
        max_tokens: int = 500,
    ) -> list[dict]:
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""
        chunk_index = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) > max_tokens * 4:
                if current_chunk:
                    body = current_chunk.strip()
                    chunks.append({
                        "id": str(uuid.uuid4()),
                        "site_id": site_id,
                        "source_url": source_url,
                        "title": title,
                        "content": body,
                        "chunk_index": chunk_index,
                        "content_hash": hashlib.sha256(body.encode()).hexdigest(),
                    })
                    chunk_index += 1
                current_chunk = para
            else:
                current_chunk += "\n\n" + para if current_chunk else para

        if current_chunk.strip():
            body = current_chunk.strip()
            chunks.append({
                "id": str(uuid.uuid4()),
                "site_id": site_id,
                "source_url": source_url,
                "title": title,
                "content": body,
                "chunk_index": chunk_index,
                "content_hash": hashlib.sha256(body.encode()).hexdigest(),
            })

        return chunks

    async def _embed_and_store(
        self,
        site_id: str,
        chunks: list[dict],
        repos,
    ):
        try:
            embed_provider = get_llm_provider(
                settings.embedding_provider,
                settings.embedding_model,
            )
        except Exception as e:
            logger.warning("Embedding provider init failed, falling back to openai", error=str(e))
            embed_provider = get_llm_provider("openai")

        contents = [c["content"] for c in chunks]

        semaphore = asyncio.Semaphore(3)

        async def _embed_batch(batch):
            async with semaphore:
                return await embed_provider.embed(batch)

        # Embed first — if this fails, nothing is stored
        try:
            batches = [contents[i : i + 100] for i in range(0, len(contents), 100)]
            if len(batches) <= 1:
                all_embeddings = await embed_provider.embed(contents) if contents else []
            else:
                results = await asyncio.gather(*[_embed_batch(b) for b in batches])
                all_embeddings = [e for batch_result in results for e in batch_result]
        except Exception as e:
            logger.error("Embedding failed, skipping chunk storage", site_id=site_id, chunk_count=len(chunks), error=str(e))
            return

        # Store vectors in ChromaDB
        try:
            await rag_engine.add_chunks(site_id, chunks, all_embeddings)
        except Exception as e:
            logger.error("Vector store failed, skipping DB storage", site_id=site_id, chunk_count=len(chunks), error=str(e))
            return

        # Store chunk metadata in DB — if this fails, clean up the vectors
        valid_fields = {"id", "site_id", "source_url", "source_type", "title", "content", "chunk_index", "content_hash", "embedding_id"}
        db_chunks = []
        for chunk in chunks:
            db_chunk = {k: v for k, v in chunk.items() if k in valid_fields}
            db_chunk["embedding_id"] = chunk["id"]
            db_chunk["source_type"] = "crawl"
            db_chunks.append(db_chunk)
        try:
            await repos.knowledge.create_many(db_chunks)
        except Exception as e:
            logger.error("DB storage failed after embedding, rolling back vectors", site_id=site_id, error=str(e))
            try:
                chunk_ids = [c["id"] for c in chunks]
                await rag_engine.delete_chunks(site_id, chunk_ids)
            except Exception as rollback_err:
                logger.error("Vector rollback also failed", site_id=site_id, error=str(rollback_err))

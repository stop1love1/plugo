import json
import re
import uuid
import asyncio
import hashlib
import fnmatch
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup
from agent.rag import rag_engine
from providers.factory import get_llm_provider
from knowledge.chunker import SemanticChunker
from config import settings
from logging_config import logger


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
    ):
        self.max_pages = max_pages
        self.delay = delay if delay is not None else settings.crawl_request_delay
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
        self.max_depth = max_depth  # 0 = unlimited
        self.exclude_patterns = exclude_patterns or []
        self.max_retries = settings.crawl_max_retries

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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.logs.append(entry)
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

    async def _parse_sitemap(self, client: httpx.AsyncClient, start_url: str, base_domain: str) -> list[str]:
        """Try to discover URLs from sitemap.xml."""
        parsed = urlparse(start_url)
        sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
        urls = []
        try:
            response = await client.get(sitemap_url)
            if response.status_code == 200 and "xml" in response.headers.get("content-type", ""):
                soup = BeautifulSoup(response.text, "html.parser")
                for loc in soup.find_all("loc"):
                    url = loc.get_text(strip=True)
                    url_parsed = urlparse(url)
                    if url_parsed.netloc == base_domain:
                        clean_url = f"{url_parsed.scheme}://{url_parsed.netloc}{url_parsed.path}"
                        if not self._is_excluded(clean_url):
                            urls.append(clean_url)
                if urls:
                    self._log(sitemap_url, "success", action=f"sitemap.xml: discovered {len(urls)} URLs")
                else:
                    self._log(sitemap_url, "skipped", action="sitemap.xml parsed but no usable URLs found")
            else:
                self._log(sitemap_url, "skipped", action="sitemap.xml not found or not XML")
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
        status_code: None=timeout, -1=error (html contains error message)."""
        last_error = None
        for attempt in range(1 + self.max_retries):
            try:
                response = await client.get(url)
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

    async def crawl_site(
        self,
        site_id: str,
        start_url: str,
        job_id: str,
        repos,
    ):
        """Crawl a website starting from the given URL."""
        base_domain = urlparse(start_url).netloc
        # Queue stores (url, depth) tuples
        queue: deque[tuple[str, int]] = deque([(start_url, 0)])
        queued_urls: set[str] = {start_url}
        self._queue_size = len(queue)
        pending_chunks: list[dict] = []
        embed_batch_size = settings.crawl_embed_batch_size

        await repos.crawl_jobs.update(job_id, {
            "status": "running",
            "current_url": start_url,
        })

        # Load already-crawled URLs for change detection
        if not self.force_recrawl:
            existing_urls = await repos.knowledge.list_crawled_urls(site_id)
            self._already_crawled_urls = {u["source_url"] for u in existing_urls if u.get("source_url")}
            if self._already_crawled_urls:
                self._log("", "success", action=f"found {len(self._already_crawled_urls)} previously crawled URLs")

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
            async with httpx.AsyncClient(
                timeout=settings.crawl_request_timeout,
                follow_redirects=True,
                verify=settings.crawl_verify_ssl,
                headers={"User-Agent": "PlugoBot/1.0 (+https://github.com/stop1love1/plugo)"},
            ) as client:
                robot_parser = await self._check_robots_txt(client, start_url)

                # Seed queue from sitemap.xml
                sitemap_urls = await self._parse_sitemap(client, start_url, base_domain)
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

                        if status_code != 200:
                            self._log(url, "skipped", error=f"HTTP {status_code}", action="non-200 response")
                            self.pages_skipped += 1
                            await self._save_progress(job_id, repos)
                            continue

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

                        chunks = self.chunker.chunk_page(soup, title, url, site_id)
                        if not chunks:
                            text = self._extract_text(soup)
                            if text.strip():
                                chunks = self._chunk_text(text, title, url, site_id)

                        pending_chunks.extend(chunks)
                        self.chunks_created += len(chunks)

                        recrawl_tag = " (re-crawl)" if is_recrawl else ""
                        depth_tag = f" [depth={depth}]" if self.max_depth > 0 else ""
                        self._log(
                            url, "success",
                            title=title,
                            chunks=len(chunks),
                            action=f"extracted {len(chunks)} chunks ({len(html)} bytes){recrawl_tag}{depth_tag}",
                        )

                        # Discover new links (same domain, respecting depth limit)
                        child_depth = depth + 1
                        if self.max_depth == 0 or child_depth <= self.max_depth:
                            for link in soup.find_all("a", href=True):
                                href = urljoin(url, link["href"])
                                parsed = urlparse(href)
                                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                                if (
                                    parsed.netloc == base_domain
                                    and clean_url not in self.visited
                                    and clean_url not in queued_urls
                                    and not self._is_excluded(clean_url)
                                ):
                                    queue.append((clean_url, child_depth))
                                    queued_urls.add(clean_url)

                        self._queue_size = len(queue)

                        # Flush chunks periodically
                        if len(pending_chunks) >= embed_batch_size:
                            await self._flush_chunks(site_id, pending_chunks, repos)
                            pending_chunks.clear()

                        await self._save_progress(job_id, repos)
                        await asyncio.sleep(self.delay)

                    except Exception as e:
                        self._log(url, "error", error=str(e), action="unexpected error")
                        self.pages_failed += 1
                        job = await repos.crawl_jobs.get_by_id(job_id)
                        error_log = (job.get("error_log") or "") + f"\n{url}: {str(e)}"
                        await repos.crawl_jobs.update(job_id, {"error_log": error_log})
                        await self._save_progress(job_id, repos)
                        continue

            # Flush remaining chunks
            if pending_chunks:
                await self._flush_chunks(site_id, pending_chunks, repos)
                pending_chunks.clear()

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
                "finished_at": datetime.now(timezone.utc),
            })

        except Exception as e:
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
                "finished_at": datetime.now(timezone.utc),
            })

    def _extract_text(self, soup: BeautifulSoup) -> str:
        for tag in soup.find_all(["nav", "footer", "header", "script", "style", "aside"]):
            tag.decompose()
        for el in soup.find_all(class_=re.compile(r"(nav|footer|sidebar|ad|menu|cookie)", re.I)):
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
                    chunks.append({
                        "id": str(uuid.uuid4()),
                        "site_id": site_id,
                        "source_url": source_url,
                        "title": title,
                        "content": current_chunk.strip(),
                        "chunk_index": chunk_index,
                    })
                    chunk_index += 1
                current_chunk = para
            else:
                current_chunk += "\n\n" + para if current_chunk else para

        if current_chunk.strip():
            chunks.append({
                "id": str(uuid.uuid4()),
                "site_id": site_id,
                "source_url": source_url,
                "title": title,
                "content": current_chunk.strip(),
                "chunk_index": chunk_index,
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

        batches = [contents[i : i + 100] for i in range(0, len(contents), 100)]
        if len(batches) <= 1:
            all_embeddings = await embed_provider.embed(contents) if contents else []
        else:
            results = await asyncio.gather(*[_embed_batch(b) for b in batches])
            all_embeddings = [e for batch_result in results for e in batch_result]

        await rag_engine.add_chunks(site_id, chunks, all_embeddings)

        valid_fields = {"id", "site_id", "source_url", "source_type", "title", "content", "chunk_index", "content_hash", "embedding_id"}
        db_chunks = []
        for chunk in chunks:
            db_chunk = {k: v for k, v in chunk.items() if k in valid_fields}
            db_chunk["embedding_id"] = chunk["id"]
            db_chunk["source_type"] = "crawl"
            db_chunks.append(db_chunk)
        await repos.knowledge.create_many(db_chunks)

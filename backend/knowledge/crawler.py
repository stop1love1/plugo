import json
import re
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional
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

    Supports graceful stop: when an admin stops the crawl, the crawler
    halts but still persists all data collected so far to the database.
    """

    def __init__(self, max_pages: int = 50, delay: float = 1.0, force_recrawl: bool = False):
        self.max_pages = max_pages
        self.delay = delay
        self.visited: set[str] = set()
        self._stopped = False
        self.chunker = SemanticChunker()
        self.logs: list[dict] = []
        self.pages_skipped = 0
        self.pages_failed = 0
        self.chunks_created = 0
        self.current_url: str | None = None
        self.force_recrawl = force_recrawl
        self._already_crawled_urls: set[str] = set()

    def stop(self):
        """Signal the crawler to stop. Data already crawled will be persisted."""
        self._stopped = True

    def _log(self, url: str, status: str, title: str = "", chunks: int = 0, error: str | None = None, action: str = ""):
        """Add a structured log entry."""
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

    async def _check_robots_txt(self, client: httpx.AsyncClient, start_url: str) -> RobotFileParser:
        """Fetch and parse robots.txt from the target domain."""
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

    async def _save_progress(self, job_id: str, repos):
        """Persist current progress and ALL logs to the job record."""
        await repos.crawl_jobs.update(job_id, {
            "pages_found": len(self.visited) + self._queue_size,
            "pages_done": len(self.visited),
            "pages_skipped": self.pages_skipped,
            "pages_failed": self.pages_failed,
            "chunks_created": self.chunks_created,
            "current_url": self.current_url,
            "crawl_log": json.dumps(self.logs),
        })

    async def crawl_site(
        self,
        site_id: str,
        start_url: str,
        job_id: str,
        repos,
    ):
        """Crawl a website starting from the given URL."""
        base_domain = urlparse(start_url).netloc
        queue = [start_url]
        self._queue_size = len(queue)
        all_chunks: list[dict] = []

        # Update job status
        await repos.crawl_jobs.update(job_id, {
            "status": "running",
            "current_url": start_url,
        })

        # Load already-crawled URLs for change detection (content-hash dedup handles duplicates at DB level)
        if not self.force_recrawl:
            existing_urls = await repos.knowledge.list_crawled_urls(site_id)
            self._already_crawled_urls = {u["source_url"] for u in existing_urls if u.get("source_url")}
            if self._already_crawled_urls:
                self._log("", "success", action=f"found {len(self._already_crawled_urls)} previously crawled URLs")

        self._log(start_url, "success", action=f"crawl started — target: {base_domain}, max {self.max_pages} pages")

        try:
            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
                verify=settings.crawl_verify_ssl,
                headers={"User-Agent": "PlugoBot/1.0 (+https://github.com/stop1love1/plugo)"},
            ) as client:
                # Fetch and parse robots.txt before crawling
                robot_parser = await self._check_robots_txt(client, start_url)

                while queue and len(self.visited) < self.max_pages:
                    # Check stop signal
                    if self._stopped:
                        self._log("", "success", action="crawl stopped by user")
                        break

                    url = queue.pop(0)
                    self._queue_size = len(queue)
                    if url in self.visited:
                        continue

                    # Check robots.txt
                    if not robot_parser.can_fetch("PlugoBot/1.0", url):
                        self._log(url, "skipped", action="blocked by robots.txt")
                        self.pages_skipped += 1
                        continue

                    self.current_url = url
                    is_recrawl = url in self._already_crawled_urls

                    try:
                        response = await client.get(url)

                        if response.status_code != 200:
                            self._log(url, "skipped", error=f"HTTP {response.status_code}", action="non-200 response")
                            self.pages_skipped += 1
                            await self._save_progress(job_id, repos)
                            continue

                        content_type = response.headers.get("content-type", "")
                        if "text/html" not in content_type:
                            self._log(url, "skipped", action=f"non-HTML content: {content_type.split(';')[0]}")
                            self.pages_skipped += 1
                            continue

                        self.visited.add(url)
                        html = response.text
                        soup = BeautifulSoup(html, "html.parser")

                        title = (soup.title.string or "").strip() if soup.title else ""

                        # Use semantic chunker for better quality
                        chunks = self.chunker.chunk_page(soup, title, url, site_id)
                        if not chunks:
                            # Fallback to simple text extraction
                            text = self._extract_text(soup)
                            if text.strip():
                                chunks = self._chunk_text(text, title, url, site_id)

                        all_chunks.extend(chunks)
                        self.chunks_created += len(chunks)

                        # Log successful page crawl with detail
                        recrawl_tag = " (re-crawl)" if is_recrawl else ""
                        self._log(
                            url, "success",
                            title=title,
                            chunks=len(chunks),
                            action=f"extracted {len(chunks)} chunks ({len(html)} bytes){recrawl_tag}",
                        )

                        # Discover new links (same domain)
                        new_links = 0
                        for link in soup.find_all("a", href=True):
                            href = urljoin(url, link["href"])
                            parsed = urlparse(href)
                            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                            if (
                                parsed.netloc == base_domain
                                and clean_url not in self.visited
                                and clean_url not in queue
                            ):
                                queue.append(clean_url)
                                new_links += 1

                        self._queue_size = len(queue)

                        # Save progress after every page
                        await self._save_progress(job_id, repos)

                        await asyncio.sleep(self.delay)

                    except httpx.TimeoutException:
                        self._log(url, "error", error="Request timed out", action="timeout after 30s")
                        self.pages_failed += 1
                        await self._save_progress(job_id, repos)
                        continue

                    except Exception as e:
                        self._log(url, "error", error=str(e), action="unexpected error")
                        self.pages_failed += 1
                        job = await repos.crawl_jobs.get_by_id(job_id)
                        error_log = (job.get("error_log") or "") + f"\n{url}: {str(e)}"
                        await repos.crawl_jobs.update(job_id, {
                            "error_log": error_log,
                        })
                        await self._save_progress(job_id, repos)
                        continue

            # Embed and store all chunks
            if all_chunks:
                self._log("", "success", action=f"embedding {len(all_chunks)} chunks into vector store...")
                await self._save_progress(job_id, repos)
                await self._embed_and_store(site_id, all_chunks, repos)
                self._log("", "success", action=f"stored {len(all_chunks)} chunks successfully")

            final_status = "stopped" if self._stopped else "completed"
            summary = (
                f"Crawl {final_status}: {len(self.visited)} pages crawled, "
                f"{self.pages_skipped} skipped, {self.pages_failed} failed, "
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

        # Parallel embedding with semaphore to respect rate limits
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

        # Store in DB via repository — strip extra fields from semantic chunker
        valid_fields = {"id", "site_id", "source_url", "source_type", "title", "content", "chunk_index", "content_hash", "embedding_id"}
        db_chunks = []
        for chunk in chunks:
            db_chunk = {k: v for k, v in chunk.items() if k in valid_fields}
            db_chunk["embedding_id"] = chunk["id"]
            db_chunk["source_type"] = "crawl"
            db_chunks.append(db_chunk)
        await repos.knowledge.create_many(db_chunks)

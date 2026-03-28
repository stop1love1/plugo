import re
import uuid
import asyncio
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup
from agent.rag import rag_engine
from providers.factory import get_llm_provider
from knowledge.chunker import SemanticChunker
from config import settings


class WebCrawler:
    """Crawls websites, extracts text, chunks, and embeds content.

    Supports graceful stop: when an admin stops the crawl, the crawler
    halts but still persists all data collected so far to the database.
    """

    def __init__(self, max_pages: int = 50, delay: float = 1.0):
        self.max_pages = max_pages
        self.delay = delay
        self.visited: set[str] = set()
        self._stopped = False
        self.chunker = SemanticChunker()

    def stop(self):
        """Signal the crawler to stop. Data already crawled will be persisted."""
        self._stopped = True

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
            else:
                # If robots.txt is not found, allow everything
                rp.parse([])
        except Exception:
            # If we can't fetch robots.txt, allow everything
            rp.parse([])
        return rp

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
        all_chunks = []

        # Update job status
        await repos.crawl_jobs.update(job_id, {"status": "running"})

        try:
            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
                headers={"User-Agent": "PlugoBot/1.0 (+https://github.com/stop1love1/plugo)"},
            ) as client:
                # Fetch and parse robots.txt before crawling
                robot_parser = await self._check_robots_txt(client, start_url)

                while queue and len(self.visited) < self.max_pages:
                    # Check stop signal — persist crawled data before stopping
                    if self._stopped:
                        break

                    url = queue.pop(0)
                    if url in self.visited:
                        continue

                    # Check robots.txt before crawling this URL
                    if not robot_parser.can_fetch("PlugoBot/1.0", url):
                        continue

                    try:
                        response = await client.get(url)
                        if response.status_code != 200:
                            continue
                        if "text/html" not in response.headers.get("content-type", ""):
                            continue

                        self.visited.add(url)
                        html = response.text
                        soup = BeautifulSoup(html, "html.parser")

                        title = soup.title.string if soup.title else ""

                        # Use semantic chunker for better quality
                        chunks = self.chunker.chunk_page(soup, title, url, site_id)
                        if not chunks:
                            # Fallback to simple text extraction
                            text = self._extract_text(soup)
                            if text.strip():
                                chunks = self._chunk_text(text, title, url, site_id)
                        all_chunks.extend(chunks)

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

                        await repos.crawl_jobs.update(job_id, {
                            "pages_found": len(self.visited) + len(queue),
                            "pages_done": len(self.visited),
                        })

                        await asyncio.sleep(self.delay)

                    except Exception as e:
                        job = await repos.crawl_jobs.get_by_id(job_id)
                        error_log = (job.get("error_log") or "") + f"\n{url}: {str(e)}"
                        await repos.crawl_jobs.update(job_id, {"error_log": error_log})
                        continue

            # Always persist crawled data, whether stopped or completed
            if all_chunks:
                await self._embed_and_store(site_id, all_chunks, repos)

            final_status = "stopped" if self._stopped else "completed"
            await repos.crawl_jobs.update(job_id, {
                "status": final_status,
                "pages_done": len(self.visited),
                "finished_at": datetime.utcnow().isoformat(),
            })

        except Exception as e:
            await repos.crawl_jobs.update(job_id, {
                "status": "failed",
                "error_log": str(e),
                "finished_at": datetime.utcnow().isoformat(),
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
        except Exception:
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

        # Store in DB via repository
        for chunk in chunks:
            chunk["embedding_id"] = chunk["id"]
            chunk["source_type"] = "crawl"
        await repos.knowledge.create_many(chunks)

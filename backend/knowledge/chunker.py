"""Semantic chunker — structure-aware text splitting with overlap."""

import hashlib
import re
import uuid
from typing import Optional
from bs4 import BeautifulSoup, Tag


class SemanticChunker:
    """Splits HTML content into semantically coherent chunks."""

    def __init__(self, max_tokens: int = 500, overlap_tokens: int = 50):
        self.max_chars = max_tokens * 4  # ~4 chars per token
        self.overlap_chars = overlap_tokens * 4

    def chunk_page(
        self,
        soup: BeautifulSoup,
        title: str,
        source_url: str,
        site_id: str,
    ) -> list[dict]:
        """Extract sections from HTML and split into overlapping chunks."""
        sections = self._extract_sections(soup)
        if not sections:
            return []

        chunks = []
        chunk_index = 0

        for section in sections:
            text = section["text"].strip()
            if not text:
                continue

            header = section.get("header", "")
            header_path = section.get("path", "")

            # If section fits in one chunk, keep it as-is
            if len(text) <= self.max_chars:
                chunks.append(self._make_chunk(
                    text, title, source_url, site_id,
                    chunk_index, header, header_path,
                ))
                chunk_index += 1
            else:
                # Split large section with overlap
                sub_chunks = self._split_with_overlap(text)
                for sub in sub_chunks:
                    chunks.append(self._make_chunk(
                        sub, title, source_url, site_id,
                        chunk_index, header, header_path,
                    ))
                    chunk_index += 1

        return chunks

    # Structural tags that must never be decomposed by the class-name filter
    _PROTECTED_TAGS = frozenset({"html", "body", "main", "article", "section"})

    def _extract_sections(self, soup: BeautifulSoup) -> list[dict]:
        """Walk the DOM and extract text grouped by heading structure."""
        # Remove unwanted elements
        for tag in soup.find_all(["nav", "footer", "header", "script", "style", "aside"]):
            tag.decompose()
        for el in soup.find_all(class_=re.compile(r"(nav|footer|sidebar|ad|menu|cookie)", re.I)):
            if el.name not in self._PROTECTED_TAGS:
                el.decompose()

        main = soup.find("main") or soup.find("article") or soup.find("body")
        if not main:
            return []

        sections = []
        current_header = ""
        current_path = ""
        current_text_parts: list[str] = []
        header_stack: list[tuple[int, str]] = []

        for element in main.descendants:
            if isinstance(element, Tag):
                # Check if it's a heading — output as markdown heading
                if element.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    # Save current section
                    text = "\n\n".join(current_text_parts).strip()
                    if text:
                        sections.append({
                            "header": current_header,
                            "path": current_path,
                            "text": text,
                        })
                        current_text_parts = []

                    level = int(element.name[1])
                    heading_text = element.get_text(strip=True)

                    # Update header stack
                    while header_stack and header_stack[-1][0] >= level:
                        header_stack.pop()
                    header_stack.append((level, heading_text))

                    current_header = heading_text
                    current_path = " > ".join(h[1] for h in header_stack)
                    # Add markdown heading to content
                    md_heading = "#" * level + " " + heading_text
                    current_text_parts.append(md_heading)

            elif isinstance(element, str):
                pass
            else:
                continue

            # Extract text from leaf elements in markdown format
            if isinstance(element, Tag) and element.name in (
                "p", "li", "td", "th", "dt", "dd", "blockquote",
                "pre", "code", "span", "div",
            ):
                # Only process leaf-like elements (those without block children)
                has_block_child = any(
                    isinstance(c, Tag) and c.name in (
                        "p", "div", "section", "article", "ul", "ol", "table",
                        "h1", "h2", "h3", "h4", "h5", "h6",
                    )
                    for c in element.children
                )
                if not has_block_child:
                    text = element.get_text(strip=True)
                    if text and len(text) > 10:
                        # Format as markdown based on element type
                        if element.name == "li":
                            text = f"- {text}"
                        elif element.name == "blockquote":
                            text = f"> {text}"
                        elif element.name in ("pre", "code"):
                            text = f"```\n{text}\n```"
                        current_text_parts.append(text)

        # Don't forget the last section
        text = "\n\n".join(current_text_parts).strip()
        if text:
            sections.append({
                "header": current_header,
                "path": current_path,
                "text": text,
            })

        return sections

    def _split_with_overlap(self, text: str) -> list[str]:
        """Split text into overlapping chunks at paragraph boundaries."""
        paragraphs = text.split("\n\n")
        chunks = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current) + len(para) > self.max_chars and current:
                chunks.append(current.strip())
                # Keep overlap from end of current chunk
                if self.overlap_chars > 0:
                    current = current[-self.overlap_chars:].strip() + "\n\n" + para
                else:
                    current = para
            else:
                current = current + "\n\n" + para if current else para

        if current.strip():
            chunks.append(current.strip())

        return chunks

    @staticmethod
    def _make_chunk(
        content: str,
        title: str,
        source_url: str,
        site_id: str,
        chunk_index: int,
        section_header: str = "",
        section_path: str = "",
    ) -> dict:
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        return {
            "id": str(uuid.uuid4()),
            "site_id": site_id,
            "source_url": source_url,
            "title": title,
            "content": content,
            "chunk_index": chunk_index,
            "content_hash": content_hash,
            "section_header": section_header,
            "section_path": section_path,
            "word_count": len(content.split()),
        }

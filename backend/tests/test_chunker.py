"""Tests for the semantic chunker (pure text/HTML processing — no I/O)."""

from bs4 import BeautifulSoup

from knowledge.chunker import SemanticChunker


def test_chunk_plain_text_empty_returns_nothing():
    chunker = SemanticChunker()
    assert chunker.chunk_plain_text("", "T", "u", "s") == []
    assert chunker.chunk_plain_text("   \n  ", "T", "u", "s") == []


def test_chunk_plain_text_short_makes_one_chunk_with_fields():
    chunker = SemanticChunker()
    chunks = chunker.chunk_plain_text("Hello world.", "Title", "https://x", "site1")
    assert len(chunks) == 1
    c = chunks[0]
    assert c["content"] == "Hello world."
    assert c["site_id"] == "site1"
    assert c["source_url"] == "https://x"
    assert c["title"] == "Title"
    assert c["chunk_index"] == 0
    assert c["content_hash"]  # sha256 present
    assert c["word_count"] == 2
    assert c["id"]


def test_chunk_plain_text_long_splits_into_multiple_chunks():
    # Tiny budget forces splitting across paragraph boundaries.
    chunker = SemanticChunker(max_tokens=5, overlap_tokens=1)
    text = "\n\n".join(f"Paragraph number {i} with enough words to matter." for i in range(8))
    chunks = chunker.chunk_plain_text(text, "T", "u", "s")
    assert len(chunks) > 1
    # chunk_index is sequential
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_chunk_page_extracts_sections_and_headings():
    html = """
    <html><body>
      <nav>menu that should be dropped</nav>
      <main>
        <h1>Getting Started</h1>
        <p>This is the introduction paragraph with plenty of content.</p>
        <h2>Installation</h2>
        <p>Run the installer and follow the prompts carefully please.</p>
        <footer>footer junk removed</footer>
      </main>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    chunker = SemanticChunker()
    chunks = chunker.chunk_page(soup, "Docs", "https://x/docs", "site1")

    assert chunks, "expected at least one chunk"
    joined = "\n".join(c["content"] for c in chunks)
    # Markdown headings are preserved.
    assert "# Getting Started" in joined
    assert "## Installation" in joined
    # nav/footer content is stripped.
    assert "menu that should be dropped" not in joined
    assert "footer junk removed" not in joined
    # A section header is recorded on at least one chunk.
    assert any(c["section_header"] for c in chunks)


def test_chunk_page_formats_list_items_as_markdown():
    html = """
    <html><body><main>
      <h1>Features</h1>
      <ul>
        <li>First feature item with sufficient length here</li>
        <li>Second feature item with sufficient length here</li>
      </ul>
    </main></body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    chunker = SemanticChunker()
    chunks = chunker.chunk_page(soup, "T", "u", "s")
    joined = "\n".join(c["content"] for c in chunks)
    assert "- First feature item" in joined


def test_chunk_page_empty_body_returns_nothing():
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert SemanticChunker().chunk_page(soup, "T", "u", "s") == []

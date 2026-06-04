"""Tests for the file text-extraction dispatcher (txt/md/csv + error paths)."""

import pytest

from knowledge.file_processor import extract_text


def test_extract_text_txt_and_md():
    assert extract_text(b"hello world", "notes.txt") == "hello world"
    assert extract_text(b"# Title\n\nbody", "readme.md") == "# Title\n\nbody"


def test_extract_text_decodes_invalid_utf8_gracefully():
    # Invalid byte is ignored rather than raising.
    out = extract_text(b"caf\xff", "x.txt")
    assert "caf" in out


def test_extract_text_csv_joins_cells_with_pipes():
    out = extract_text(b"a,b,c\n1,2,3\n", "data.csv")
    assert "a | b | c" in out
    assert "1 | 2 | 3" in out


def test_extract_text_csv_truncates_huge_files():
    from knowledge.file_processor import MAX_CSV_ROWS

    rows = "\n".join(f"{i},x" for i in range(MAX_CSV_ROWS + 50))
    out = extract_text(rows.encode(), "big.csv")
    assert "truncated" in out


def test_extract_text_unsupported_type_raises():
    with pytest.raises(ValueError, match="Unsupported file type"):
        extract_text(b"data", "archive.zip")


def test_extract_text_corrupt_pdf_raises_valueerror():
    """A non-PDF byte stream with a .pdf name should surface a clean ValueError."""
    pytest.importorskip("pypdf")
    with pytest.raises(ValueError, match="Could not read PDF"):
        extract_text(b"this is definitely not a pdf", "broken.pdf")

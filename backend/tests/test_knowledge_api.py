"""Tests for Knowledge management flow."""

import uuid

import pytest


@pytest.fixture
async def test_chunk(db_repos, test_site):
    """Create a test knowledge chunk."""
    chunk_id = str(uuid.uuid4())
    chunk = await db_repos.knowledge.create({
        "id": chunk_id,
        "site_id": test_site["id"],
        "source_url": "https://example.com/page1",
        "source_type": "crawl",
        "title": "Test Chunk",
        "content": "This is a test knowledge chunk with some content for testing purposes.",
        "embedding_id": chunk_id,
    })
    yield chunk
    try:
        await db_repos.knowledge.delete(chunk_id)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_list_knowledge(client, auth_headers, test_site, test_chunk):
    """GET /api/knowledge should return paginated chunks."""
    response = await client.get(
        f"/api/knowledge?site_id={test_site['id']}",
        headers=auth_headers,
    )
    assert response.status_code == 200

    data = response.json()
    assert "chunks" in data


@pytest.mark.asyncio
async def test_list_knowledge_without_auth(client, test_site):
    """GET /api/knowledge without auth should return 401."""
    response = await client.get(f"/api/knowledge?site_id={test_site['id']}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_knowledge_pagination(client, auth_headers, test_site):
    """GET /api/knowledge should respect page and per_page params."""
    response = await client.get(
        f"/api/knowledge?site_id={test_site['id']}&page=1&per_page=5",
        headers=auth_headers,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_chunk_by_id(client, auth_headers, test_chunk):
    """GET /api/knowledge/{chunk_id} should return full chunk."""
    response = await client.get(
        f"/api/knowledge/{test_chunk['id']}",
        headers=auth_headers,
    )
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == test_chunk["id"]
    assert data["title"] == "Test Chunk"
    assert "content" in data


@pytest.mark.asyncio
async def test_get_chunk_not_found(client, auth_headers):
    """GET /api/knowledge/{chunk_id} with invalid id should return 404."""
    response = await client.get(
        "/api/knowledge/nonexistent-chunk-id",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_chunk(client, auth_headers, test_chunk):
    """PUT /api/knowledge/{chunk_id} should update chunk fields."""
    response = await client.put(
        f"/api/knowledge/{test_chunk['id']}",
        json={"title": "Updated Title"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Chunk updated"


@pytest.mark.asyncio
async def test_update_chunk_no_fields(client, auth_headers, test_chunk):
    """PUT /api/knowledge/{chunk_id} with no fields should return 400."""
    response = await client.put(
        f"/api/knowledge/{test_chunk['id']}",
        json={},
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_delete_chunk(client, auth_headers, db_repos, test_site):
    """DELETE /api/knowledge/{chunk_id} should delete the chunk."""
    chunk_id = str(uuid.uuid4())
    await db_repos.knowledge.create({
        "id": chunk_id,
        "site_id": test_site["id"],
        "source_type": "manual",
        "title": "To Delete",
        "content": "Delete me",
        "embedding_id": chunk_id,
    })

    response = await client.delete(
        f"/api/knowledge/{chunk_id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Chunk deleted"


@pytest.mark.asyncio
async def test_delete_chunk_not_found(client, auth_headers):
    """DELETE /api/knowledge/{chunk_id} with invalid id should return 404."""
    response = await client.delete(
        "/api/knowledge/nonexistent-chunk-id",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_bulk_delete_chunks(client, auth_headers, db_repos, test_site):
    """POST /api/knowledge/bulk-delete should delete multiple chunks."""
    ids = []
    for i in range(3):
        chunk_id = str(uuid.uuid4())
        await db_repos.knowledge.create({
            "id": chunk_id,
            "site_id": test_site["id"],
            "source_type": "manual",
            "title": f"Bulk Delete {i}",
            "content": f"Content {i}",
            "embedding_id": chunk_id,
        })
        ids.append(chunk_id)

    response = await client.post(
        "/api/knowledge/bulk-delete",
        json={"chunk_ids": ids},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["deleted"] == 3


@pytest.mark.asyncio
async def test_upload_txt_file(client, auth_headers, test_site):
    """POST /api/knowledge/upload should accept .txt files."""
    content = b"This is a test text file with some knowledge content."

    response = await client.post(
        f"/api/knowledge/upload?site_id={test_site['id']}",
        files={"file": ("test.txt", content, "text/plain")},
        headers=auth_headers,
    )
    assert response.status_code == 200

    data = response.json()
    assert data["filename"] == "test.txt"
    assert data["message"] == "File uploaded"


@pytest.mark.asyncio
async def test_upload_md_file(client, auth_headers, test_site):
    """POST /api/knowledge/upload should accept .md files."""
    content = b"# Test Markdown\n\nSome markdown content."

    response = await client.post(
        f"/api/knowledge/upload?site_id={test_site['id']}",
        files={"file": ("test.md", content, "text/markdown")},
        headers=auth_headers,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_upload_unsupported_format(client, auth_headers, test_site):
    """POST /api/knowledge/upload should reject unsupported file types."""
    content = b"<html><body>Not supported</body></html>"

    response = await client.post(
        f"/api/knowledge/upload?site_id={test_site['id']}",
        files={"file": ("test.html", content, "text/html")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "Supported formats" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_empty_file(client, auth_headers, test_site):
    """POST /api/knowledge/upload should reject empty files."""
    response = await client.post(
        f"/api/knowledge/upload?site_id={test_site['id']}",
        files={"file": ("empty.txt", b"   ", "text/plain")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()

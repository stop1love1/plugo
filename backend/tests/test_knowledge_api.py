"""Tests for Knowledge management flow."""

import contextlib
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
    with contextlib.suppress(Exception):
        await db_repos.knowledge.delete(chunk_id)


@pytest.mark.asyncio
async def test_list_knowledge_without_auth(client, test_site):
    """GET /api/knowledge without auth should return 401."""
    response = await client.get(f"/api/knowledge?site_id={test_site['id']}")
    assert response.status_code == 401


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
    assert "File uploaded" in data["message"]


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


# ---------- Extended coverage: pagination, search, URL/site-scope delete ----------


@pytest.mark.asyncio
async def test_list_knowledge_pagination_respects_limits(client, auth_headers, db_repos, test_site):
    """Create 25 chunks; page 1 (per_page=20) has 20, page 2 has 5."""
    for i in range(25):
        cid = str(uuid.uuid4())
        await db_repos.knowledge.create({
            "id": cid,
            "site_id": test_site["id"],
            "source_url": f"https://example.com/p{i}",
            "source_type": "crawl",
            "title": f"Title {i:02d}",
            "content": f"Body {i:02d}",
            "embedding_id": cid,
        })

    r1 = await client.get(
        f"/api/knowledge?site_id={test_site['id']}&page=1&per_page=20",
        headers=auth_headers,
    )
    r2 = await client.get(
        f"/api/knowledge?site_id={test_site['id']}&page=2&per_page=20",
        headers=auth_headers,
    )
    assert r1.status_code == 200 and r2.status_code == 200
    # The fixture leaves other sites' chunks alone, but the site_id filter
    # scopes us; total should equal the 25 we just inserted.
    d1 = r1.json()
    d2 = r2.json()
    assert d1["total"] >= 25
    assert len(d1["chunks"]) == 20
    assert len(d2["chunks"]) >= 5


@pytest.mark.asyncio
async def test_list_knowledge_search_filters_by_title(client, auth_headers, db_repos, test_site):
    """Search term must match either title or content; non-matching rows excluded."""
    hit_id = str(uuid.uuid4())
    miss_id = str(uuid.uuid4())
    await db_repos.knowledge.create({
        "id": hit_id, "site_id": test_site["id"],
        "source_type": "manual", "title": "Pineapple Guide",
        "content": "Tropical fruit knowledge.", "embedding_id": hit_id,
    })
    await db_repos.knowledge.create({
        "id": miss_id, "site_id": test_site["id"],
        "source_type": "manual", "title": "Apple Guide",
        "content": "Temperate fruit knowledge.", "embedding_id": miss_id,
    })

    r = await client.get(
        f"/api/knowledge?site_id={test_site['id']}&search=Pineapple",
        headers=auth_headers,
    )
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()["chunks"]}
    assert hit_id in ids
    assert miss_id not in ids


@pytest.mark.asyncio
async def test_delete_by_url_removes_all_chunks_for_that_url(client, auth_headers, db_repos, test_site):
    """3 chunks share a source_url; delete-by-URL must leave 0 rows for it."""
    url = f"https://example.com/doc-{uuid.uuid4().hex[:6]}"
    for i in range(3):
        cid = str(uuid.uuid4())
        await db_repos.knowledge.create({
            "id": cid, "site_id": test_site["id"],
            "source_url": url, "source_type": "crawl",
            "title": f"Chunk {i}", "content": f"Body {i}",
            "chunk_index": i, "embedding_id": cid,
        })

    r = await client.post(
        "/api/knowledge/url/delete",
        json={"site_id": test_site["id"], "source_url": url},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["deleted"] == 3

    # Nothing left under that URL.
    remaining = await db_repos.knowledge.list_by_url(test_site["id"], url)
    assert remaining == []


@pytest.mark.asyncio
async def test_delete_all_by_site_cascade_cleanup(db_repos, test_site):
    """Repo-level cascade: delete_all_by_site wipes every chunk for the site."""
    for _ in range(4):
        cid = str(uuid.uuid4())
        await db_repos.knowledge.create({
            "id": cid, "site_id": test_site["id"],
            "source_type": "manual", "title": "x",
            "content": "x", "embedding_id": cid,
        })
    deleted = await db_repos.knowledge.delete_all_by_site(test_site["id"])
    assert deleted >= 4

    page = await db_repos.knowledge.list_by_site(test_site["id"], page=1, per_page=50)
    assert page["total"] == 0


# ---------- Reindex endpoint ----------


@pytest.mark.asyncio
async def test_reindex_endpoint_rebuilds_embeddings(client, auth_headers, db_repos, test_site, monkeypatch):
    """POST /api/knowledge/reindex: 5 chunks → all re-embedded and re-added.

    The real embed provider is swapped for a deterministic stub. We assert
    that rag_engine.add_chunks was called with exactly the chunk ids we
    seeded (so the reindex path touched every row), and that the endpoint
    returns the expected summary."""
    # Seed 5 chunks.
    seeded_ids = []
    for i in range(5):
        cid = str(uuid.uuid4())
        await db_repos.knowledge.create({
            "id": cid, "site_id": test_site["id"],
            "source_url": f"https://example.com/r{i}", "source_type": "manual",
            "title": f"R{i}", "content": f"Content {i}",
            "chunk_index": i, "embedding_id": cid,
        })
        seeded_ids.append(cid)

    class _StubEmbedProvider:
        async def embed(self, contents):
            # Deterministic: length of content as the only dim.
            return [[float(len(c))] for c in contents]

    added_chunks: list[dict] = []
    added_embeddings: list[list[list[float]]] = []

    async def _capture_add(site_id, chunks, embeddings):
        added_chunks.extend(chunks)
        added_embeddings.append(embeddings)
        return [c["id"] for c in chunks]

    async def _noop_delete(site_id):
        return None

    monkeypatch.setattr("routers.knowledge.get_llm_provider", lambda *a, **k: _StubEmbedProvider())
    monkeypatch.setattr("routers.knowledge.rag_engine.add_chunks", _capture_add)
    monkeypatch.setattr("routers.knowledge.rag_engine.delete_site", _noop_delete)

    r = await client.post(
        f"/api/knowledge/reindex?site_id={test_site['id']}",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["chunks_reindexed"] == 5
    assert body["elapsed_seconds"] >= 0.0

    # Every seeded id shows up in the vectors we tried to add.
    added_ids = {c["id"] for c in added_chunks}
    for sid in seeded_ids:
        assert sid in added_ids


@pytest.mark.asyncio
async def test_reindex_empty_site_is_noop(client, auth_headers, db_repos, test_site, monkeypatch):
    """Empty site → 0 chunks, no embed calls, 200 OK."""
    calls = {"embed": 0, "add": 0}

    class _StubEmbed:
        async def embed(self, contents):
            calls["embed"] += 1
            return []

    async def _add(site_id, chunks, embeddings):
        calls["add"] += 1
        return []

    async def _noop_delete(site_id):
        return None

    monkeypatch.setattr("routers.knowledge.get_llm_provider", lambda *a, **k: _StubEmbed())
    monkeypatch.setattr("routers.knowledge.rag_engine.add_chunks", _add)
    monkeypatch.setattr("routers.knowledge.rag_engine.delete_site", _noop_delete)

    r = await client.post(
        f"/api/knowledge/reindex?site_id={test_site['id']}",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["chunks_reindexed"] == 0
    assert calls["embed"] == 0
    assert calls["add"] == 0


@pytest.mark.asyncio
async def test_reindex_requires_auth(client, test_site):
    r = await client.post(f"/api/knowledge/reindex?site_id={test_site['id']}")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_reindex_site_handles_more_than_sync_max(db_repos, test_site, monkeypatch):
    """_reindex_site must NOT truncate when called directly (CLI path).

    Regression guard: the helper used to `list_by_site(per_page=REINDEX_SYNC_MAX + 1)`,
    which silently dropped rows past that cap while still wiping the Chroma
    collection — data loss for large sites. The helper now paginates, so
    every chunk should be re-embedded regardless of site size. We drive the
    cap down to 5 via monkeypatch and seed 12 chunks to exercise the loop
    cheaply.
    """
    from routers import knowledge as knowledge_module

    # Shrink the cap so we don't need 1000+ rows to cross it.
    monkeypatch.setattr(knowledge_module, "REINDEX_SYNC_MAX", 5)
    # Page size must be < total so we actually loop (cover the pagination).
    monkeypatch.setattr(knowledge_module, "REINDEX_FETCH_PAGE_SIZE", 4)

    seeded_ids: list[str] = []
    for i in range(12):
        cid = str(uuid.uuid4())
        await db_repos.knowledge.create({
            "id": cid, "site_id": test_site["id"],
            "source_url": f"https://example.com/big{i}", "source_type": "manual",
            "title": f"Big {i}", "content": f"Content {i}",
            "chunk_index": i, "embedding_id": cid,
        })
        seeded_ids.append(cid)

    added_ids: list[str] = []
    embed_call_count = {"n": 0}

    class _StubEmbed:
        async def embed(self, contents):
            embed_call_count["n"] += len(contents)
            return [[float(len(c))] for c in contents]

    async def _capture_add(site_id, chunks, embeddings):
        added_ids.extend(c["id"] for c in chunks)
        return [c["id"] for c in chunks]

    async def _noop_delete(site_id):
        return None

    monkeypatch.setattr("routers.knowledge.get_llm_provider", lambda *a, **k: _StubEmbed())
    monkeypatch.setattr("routers.knowledge.rag_engine.add_chunks", _capture_add)
    monkeypatch.setattr("routers.knowledge.rag_engine.delete_site", _noop_delete)

    result = await knowledge_module._reindex_site(test_site["id"], db_repos)

    # All 12 chunks must have been re-embedded AND re-added to the vector store.
    assert result["chunks_reindexed"] == 12, result
    assert embed_call_count["n"] == 12
    assert set(added_ids) == set(seeded_ids)


@pytest.mark.asyncio
async def test_reindex_creates_audit_log(client, auth_headers, db_repos, test_site, monkeypatch):
    class _StubEmbed:
        async def embed(self, contents):
            return [[0.1] for _ in contents]

    async def _add(site_id, chunks, embeddings):
        return [c["id"] for c in chunks]

    async def _noop_delete(site_id):
        return None

    monkeypatch.setattr("routers.knowledge.get_llm_provider", lambda *a, **k: _StubEmbed())
    monkeypatch.setattr("routers.knowledge.rag_engine.add_chunks", _add)
    monkeypatch.setattr("routers.knowledge.rag_engine.delete_site", _noop_delete)

    cid = str(uuid.uuid4())
    await db_repos.knowledge.create({
        "id": cid, "site_id": test_site["id"],
        "source_type": "manual", "title": "x",
        "content": "x", "embedding_id": cid,
    })
    r = await client.post(
        f"/api/knowledge/reindex?site_id={test_site['id']}",
        headers=auth_headers,
    )
    assert r.status_code == 200

    audit = await db_repos.audit_logs.list_by_site(page=1, per_page=50)
    assert any(
        log.get("action") == "reindex" and log.get("resource_type") == "knowledge"
        for log in audit.get("logs", [])
    )

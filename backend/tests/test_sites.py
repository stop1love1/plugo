"""Tests for Sites CRUD flow and the per-site origin validator."""

import contextlib
import uuid

import pytest

from utils.cors import validate_site_origin


@pytest.mark.asyncio
async def test_create_site(client, auth_headers):
    """POST /api/sites should create a new site."""
    response = await client.post(
        "/api/sites",
        json={
            "name": "My Test Site",
            "url": "https://mysite.com",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "My Test Site"
    assert data["url"] == "https://mysite.com"
    assert "id" in data
    assert "token" in data
    assert data["llm_provider"] == "claude"
    assert data["primary_color"] == "#6366f1"
    # Fresh sites must not be auto-approved — approval is an explicit admin action.
    assert data["is_approved"] is False

    # Cleanup
    await client.delete(f"/api/sites/{data['id']}", headers=auth_headers)


@pytest.mark.parametrize(
    "overrides",
    [
        {"llm_provider": "invalid_provider"},
        {"primary_color": "not-a-color"},
        {"name": ""},
    ],
)
@pytest.mark.asyncio
async def test_create_site_rejects_invalid_payload(client, auth_headers, overrides):
    """POST /api/sites with invalid provider / color / empty name should 422."""
    payload = {"name": "Bad Site", "url": "https://example.com", **overrides}
    response = await client.post("/api/sites", json=payload, headers=auth_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_sites(client, auth_headers, test_site):
    """GET /api/sites should return list of sites."""
    response = await client.get("/api/sites", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert any(s["id"] == test_site["id"] for s in data)


@pytest.mark.asyncio
async def test_get_site_by_id(client, auth_headers, test_site):
    """GET /api/sites/{site_id} should return site details."""
    response = await client.get(f"/api/sites/{test_site['id']}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == test_site["id"]
    assert data["name"] == test_site["name"]


@pytest.mark.asyncio
async def test_get_site_not_found(client, auth_headers):
    """GET /api/sites/{site_id} with invalid id should return 404."""
    response = await client.get("/api/sites/nonexistent-id", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_site(client, auth_headers, test_site):
    """PUT /api/sites/{site_id} should update site fields."""
    response = await client.put(
        f"/api/sites/{test_site['id']}",
        json={
            "name": "Updated Name",
            "primary_color": "#ff0000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["primary_color"] == "#ff0000"


@pytest.mark.asyncio
async def test_update_site_not_found(client, auth_headers):
    """PUT /api/sites/{site_id} with invalid id should return 404."""
    response = await client.put(
        "/api/sites/nonexistent-id",
        json={
            "name": "Ghost Site",
        },
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_site_rejects_non_working_model(client, auth_headers, test_site, monkeypatch):
    """PUT /api/sites/{site_id} should reject model configs that fail verification."""

    async def fake_get_llm_provider(provider: str | None = None, model: str | None = None):
        raise AssertionError("This helper should not be awaited")

    class BrokenProvider:
        async def chat(self, messages, system_prompt="", tools=None, temperature=0.7):
            raise RuntimeError("Model check failed")

    monkeypatch.setattr("providers.factory.get_llm_provider", lambda provider=None, model=None: BrokenProvider())

    response = await client.put(
        f"/api/sites/{test_site['id']}",
        json={"llm_provider": "openai", "llm_model": "bad-model"},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "bad-model" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_site(client, auth_headers, db_repos):
    """DELETE /api/sites/{site_id} should delete the site."""
    # Create a site to delete
    site = await db_repos.sites.create(
        {
            "name": "To Delete",
            "url": "https://delete.me",
        }
    )

    response = await client.delete(f"/api/sites/{site['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Site deleted"

    # Verify it's gone
    response = await client.get(f"/api/sites/{site['id']}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_site_not_found(client, auth_headers):
    """DELETE /api/sites/{site_id} with invalid id should return 404."""
    response = await client.delete("/api/sites/nonexistent-id", headers=auth_headers)
    assert response.status_code == 404


# --- Cascade cleanup on site deletion ---


@contextlib.asynccontextmanager
async def _repos():
    """Repos on their own session, closed afterwards.

    Deliberately not the `db_repos` fixture: the post-delete assertions must run on
    a session that has never seen the seeded rows, or the ORM identity map could
    hand back a row the request already deleted.
    """
    from repositories import create_repos

    repos = await create_repos()
    try:
        yield repos
    finally:
        await repos.close()


async def _seed_site_with_dependents() -> dict:
    """Create a site plus one row in every table that hangs off it."""
    async with _repos() as repos:
        site = await repos.sites.create({"name": "Cascade Site", "url": "https://cascade.test"})
        site_id = site["id"]
        chunk = await repos.knowledge.create(
            {
                "site_id": site_id,
                "source_url": "https://cascade.test/page",
                "title": "Page",
                "content": "some knowledge",
                "content_hash": uuid.uuid4().hex,
            }
        )
        tool = await repos.tools.create(
            {
                "site_id": site_id,
                "name": "lookup",
                "description": "Look something up",
                "method": "GET",
                "url": "https://api.cascade.test/lookup",
            }
        )
        session = await repos.chat_sessions.create(
            {"site_id": site_id, "visitor_id": "visitor-1", "messages": [{"role": "user", "content": "hi"}]}
        )
        job = await repos.crawl_jobs.create({"site_id": site_id, "start_url": "https://cascade.test"})
        memory = await repos.visitor_memories.create(
            {"visitor_id": "visitor-1", "site_id": site_id, "category": "identity", "key": "name", "value": "Ada"}
        )
        summary = await repos.conversation_summaries.create(
            {"session_id": session["id"], "site_id": site_id, "summary_text": "they said hi"}
        )
        flow = await repos.flows.create({"site_id": site_id, "name": "Onboarding"})
        step = await repos.flow_steps.create({"flow_id": flow["id"], "step_order": 1, "title": "Step one"})
    return {
        "site": site,
        "chunk": chunk,
        "tool": tool,
        "session": session,
        "job": job,
        "memory": memory,
        "summary": summary,
        "flow": flow,
        "step": step,
    }


async def _assert_site_and_dependents_gone(seeded: dict) -> None:
    """Re-read everything the site owned and assert none of it survived."""
    async with _repos() as repos:
        site_id = seeded["site"]["id"]
        assert await repos.sites.get_by_id(site_id) is None
        assert (await repos.knowledge.list_by_site(site_id))["total"] == 0
        assert await repos.tools.list_by_site(site_id) == []
        assert await repos.chat_sessions.list_by_site(site_id) == []
        assert await repos.crawl_jobs.list_by_site(site_id) == []
        assert await repos.visitor_memories.list_by_site(site_id) == []
        assert await repos.conversation_summaries.get_by_session(seeded["session"]["id"]) is None
        assert await repos.flows.list_by_site(site_id) == []
        assert await repos.flow_steps.list_by_flow(seeded["flow"]["id"]) == []


@pytest.mark.asyncio
async def test_delete_site_cascades_dependent_records(client, auth_headers, monkeypatch):
    """DELETE /api/sites/{id} must take every site-scoped record with it, and drop
    the site's vector collection."""
    from agent.rag import rag_engine

    dropped_collections: list[str] = []

    async def _record_delete(site_id: str) -> None:
        dropped_collections.append(site_id)

    monkeypatch.setattr(rag_engine, "delete_site", _record_delete)

    seeded = await _seed_site_with_dependents()

    response = await client.delete(f"/api/sites/{seeded['site']['id']}", headers=auth_headers)
    assert response.status_code == 200

    await _assert_site_and_dependents_gone(seeded)
    assert dropped_collections == [seeded["site"]["id"]]


@pytest.mark.asyncio
async def test_delete_site_survives_vector_store_failure(client, auth_headers, monkeypatch):
    """A ChromaDB failure is secondary: the DB deletion still commits and the
    request still succeeds."""
    from agent.rag import rag_engine

    async def _boom(site_id: str) -> None:
        raise RuntimeError("chroma is down")

    monkeypatch.setattr(rag_engine, "delete_site", _boom)

    seeded = await _seed_site_with_dependents()

    response = await client.delete(f"/api/sites/{seeded['site']['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Site deleted"

    await _assert_site_and_dependents_gone(seeded)


@pytest.mark.asyncio
async def test_delete_site_leaves_other_sites_untouched(client, auth_headers, monkeypatch):
    """The cascade must be scoped to the deleted site — this is a multi-tenant store."""
    from agent.rag import rag_engine

    async def _noop(site_id: str) -> None:
        return None

    monkeypatch.setattr(rag_engine, "delete_site", _noop)

    doomed = await _seed_site_with_dependents()
    keeper = await _seed_site_with_dependents()

    response = await client.delete(f"/api/sites/{doomed['site']['id']}", headers=auth_headers)
    assert response.status_code == 200

    await _assert_site_and_dependents_gone(doomed)

    async with _repos() as repos:
        keeper_id = keeper["site"]["id"]
        assert (await repos.knowledge.list_by_site(keeper_id))["total"] == 1
        assert len(await repos.tools.list_by_site(keeper_id)) == 1
        assert len(await repos.chat_sessions.list_by_site(keeper_id)) == 1
        assert len(await repos.crawl_jobs.list_by_site(keeper_id)) == 1
        assert len(await repos.visitor_memories.list_by_site(keeper_id)) == 1
        assert await repos.conversation_summaries.get_by_session(keeper["session"]["id"]) is not None
        assert len(await repos.flows.list_by_site(keeper_id)) == 1
        assert len(await repos.flow_steps.list_by_flow(keeper["flow"]["id"])) == 1
        await repos.sites.delete(keeper_id)


# --- MongoDB cascade (Mongo has no FKs, so MongoSiteRepo.delete does it by hand) ---
# The suite runs against SQLite only, so the Mongo path is covered by a unit test
# over MongoSiteRepo.delete driven by an in-memory stand-in for the Motor database.


class _FakeDeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


class _FakeCollection:
    """Minimal Motor-collection stand-in: equality filters plus `$in`."""

    def __init__(self, docs: list[dict]):
        self.docs = docs

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        for key, condition in query.items():
            if isinstance(condition, dict) and "$in" in condition:
                if doc.get(key) not in condition["$in"]:
                    return False
            elif doc.get(key) != condition:
                return False
        return True

    async def find_one(self, query: dict, _projection: dict | None = None) -> dict | None:
        return next((doc for doc in self.docs if self._matches(doc, query)), None)

    def find(self, query: dict, _projection: dict | None = None):
        matched = [doc for doc in self.docs if self._matches(doc, query)]

        async def _cursor():
            for doc in matched:
                yield doc

        return _cursor()

    async def delete_many(self, query: dict) -> _FakeDeleteResult:
        kept = [doc for doc in self.docs if not self._matches(doc, query)]
        removed = len(self.docs) - len(kept)
        self.docs[:] = kept
        return _FakeDeleteResult(removed)

    async def delete_one(self, query: dict) -> _FakeDeleteResult:
        for index, doc in enumerate(self.docs):
            if self._matches(doc, query):
                del self.docs[index]
                return _FakeDeleteResult(1)
        return _FakeDeleteResult(0)


class _FakeMongoDB:
    def __init__(self, collections: dict[str, list[dict]]):
        self._collections = {name: _FakeCollection(docs) for name, docs in collections.items()}

    def __getitem__(self, name: str) -> _FakeCollection:
        return self._collections.setdefault(name, _FakeCollection([]))


@pytest.mark.asyncio
async def test_mongo_site_repo_delete_cascades():
    """MongoSiteRepo.delete must clear every site-scoped collection itself."""
    from repositories.mongo_repo import MongoSiteRepo

    db = _FakeMongoDB(
        {
            "sites": [{"_id": "s1"}, {"_id": "s2"}],
            "knowledge_chunks": [{"_id": "k1", "site_id": "s1"}, {"_id": "k2", "site_id": "s2"}],
            "chat_sessions": [{"_id": "c1", "site_id": "s1"}],
            "tools": [{"_id": "t1", "site_id": "s1"}],
            "crawl_jobs": [{"_id": "j1", "site_id": "s1"}],
            "visitor_memories": [{"_id": "m1", "site_id": "s1"}],
            "conversation_summaries": [{"_id": "cs1", "site_id": "s1"}],
            "flows": [{"_id": "f1", "site_id": "s1"}, {"_id": "f2", "site_id": "s2"}],
            "flow_steps": [{"_id": "st1", "flow_id": "f1"}, {"_id": "st2", "flow_id": "f2"}],
        }
    )

    assert await MongoSiteRepo(db).delete("s1") is True

    assert db["sites"].docs == [{"_id": "s2"}]
    assert db["knowledge_chunks"].docs == [{"_id": "k2", "site_id": "s2"}]
    for name in ("chat_sessions", "tools", "crawl_jobs", "visitor_memories", "conversation_summaries"):
        assert db[name].docs == []
    assert db["flows"].docs == [{"_id": "f2", "site_id": "s2"}]
    # Steps hang off flows, not sites: only the deleted site's flow loses its steps.
    assert db["flow_steps"].docs == [{"_id": "st2", "flow_id": "f2"}]


@pytest.mark.asyncio
async def test_mongo_site_repo_delete_unknown_site_touches_nothing():
    """An unknown site id must report False and leave every collection alone."""
    from repositories.mongo_repo import MongoSiteRepo

    db = _FakeMongoDB(
        {
            "sites": [{"_id": "s1"}],
            "knowledge_chunks": [{"_id": "k1", "site_id": "s1"}],
        }
    )

    assert await MongoSiteRepo(db).delete("ghost") is False

    assert db["sites"].docs == [{"_id": "s1"}]
    assert db["knowledge_chunks"].docs == [{"_id": "k1", "site_id": "s1"}]


@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/api/sites"),
        ("GET", "/api/sites"),
        ("PUT", "/api/sites/any-id"),
    ],
)
@pytest.mark.asyncio
async def test_sites_endpoints_require_auth(client, method, path):
    """All admin site endpoints must reject unauthenticated requests with 401."""
    response = await client.request(method, path, json={"name": "x", "url": "https://x.com"})
    assert response.status_code == 401


# --- Approval flow ---
# (is_approved=False default is asserted by test_create_site above.)


@pytest.mark.asyncio
async def test_approve_site(client, auth_headers, test_site):
    """PUT /api/sites/{id}/approval should approve a site."""
    response = await client.put(
        f"/api/sites/{test_site['id']}/approval",
        json={"is_approved": True},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["is_approved"] is True


@pytest.mark.asyncio
async def test_revoke_site_approval(client, auth_headers, test_site):
    """PUT /api/sites/{id}/approval with False should revoke approval."""
    # First approve
    await client.put(
        f"/api/sites/{test_site['id']}/approval",
        json={"is_approved": True},
        headers=auth_headers,
    )
    # Then revoke
    response = await client.put(
        f"/api/sites/{test_site['id']}/approval",
        json={"is_approved": False},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["is_approved"] is False


@pytest.mark.asyncio
async def test_approve_site_not_found(client, auth_headers):
    """PUT /api/sites/{id}/approval with invalid id should return 404."""
    response = await client.put(
        "/api/sites/nonexistent-id/approval",
        json={"is_approved": True},
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_approve_site_viewer_forbidden(client):
    """PUT /api/sites/{id}/approval as viewer should return 403."""
    from auth import create_access_token

    token = create_access_token(subject="viewer_user", role="viewer")
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.put(
        "/api/sites/any-site-id/approval",
        json={"is_approved": True},
        headers=headers,
    )
    assert response.status_code == 403


# --- validate_site_origin (per-site origin gate for widget routes) ---


@pytest.mark.parametrize(
    "site, origin, expected",
    [
        # Empty allowed_domains → permissive (legacy behaviour).
        ({"allowed_domains": ""}, "https://evil.com", True),
        # Exact host match.
        ({"allowed_domains": "example.com"}, "https://example.com", True),
        # Subdomain match (deep + shallow both allowed).
        ({"allowed_domains": "example.com"}, "https://sub.example.com", True),
        # Non-match: sibling / substring domains must be rejected.
        ({"allowed_domains": "example.com"}, "https://evilexample.com", False),
        # Configured allowlist but no Origin header → deny.
        ({"allowed_domains": "example.com"}, None, False),
        # Malformed origin (no hostname) → deny.
        ({"allowed_domains": "example.com"}, "not-a-url", False),
        # `Origin: null` (sandboxed iframes, file://) with a configured
        # allowlist → deny. This is a deliberate security contract: opaque
        # origins cannot be attributed to a tenant, so they must not pass.
        ({"allowed_domains": "example.com"}, "null", False),
        # Same `Origin: null` with an EMPTY allowlist → allow (permissive
        # dev path; the contract only tightens once a site opts in).
        ({"allowed_domains": ""}, "null", True),
    ],
)
def test_validate_site_origin(site, origin, expected):
    assert validate_site_origin(site, origin) is expected


def test_validate_site_origin_none_site_is_permissive():
    # Defensive: if the caller passes None (site lookup returned None and
    # they forgot to 404 first), don't raise.
    assert validate_site_origin(None, "https://anywhere.com") is True

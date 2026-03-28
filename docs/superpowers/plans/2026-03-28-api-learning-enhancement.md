# API Learning & Project Understanding Enhancement

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the bot from a passive knowledge reader into an intelligent agent that can learn API docs, execute API operations, understand project flows, and deeply comprehend a project's functionalities.

**Architecture:** Three new subsystems: (1) OpenAPI/Swagger spec parser that auto-generates tools + structured API knowledge, (2) Streaming tool calling so the widget can actually execute API actions, (3) Flow/workflow learning that teaches the bot multi-step processes. All integrate into the existing RAG + tool calling pipeline.

**Tech Stack:** Python (FastAPI, httpx, pyyaml), existing ChromaDB/RAG, existing provider abstraction, React (dashboard UI)

---

## Current Problems Identified

1. **Tools are manually created one-by-one** — admin must hand-type each endpoint's name, URL, method, params. No way to import from API docs.
2. **Streaming doesn't support tool calling** — `stream_response()` yields tokens but never executes tools. The widget uses streaming, so **tools are completely broken in production**.
3. **No API documentation understanding** — the crawler treats API docs like any web page. No special handling for endpoint descriptions, request/response schemas, auth flows.
4. **No flow/workflow concept** — the bot answers individual questions but can't guide users through multi-step processes (e.g., "how to create an order" = search → add to cart → checkout).
5. **Embedding provider mismatch** — `core.py:107` hardcodes OpenAI for query embeddings while crawl uses `settings.embedding_provider`.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `backend/knowledge/openapi_parser.py` | Create | Parse OpenAPI/Swagger specs → tools + knowledge chunks |
| `backend/knowledge/api_chunker.py` | Create | API-aware chunking: endpoints, params, responses, auth |
| `backend/knowledge/flow_extractor.py` | Create | Extract and store multi-step workflows |
| `backend/models/flow.py` | Create | Flow/workflow data model |
| `backend/routers/api_import.py` | Create | API endpoints for OpenAPI import + flow management |
| `backend/agent/core.py` | Modify | Fix streaming tool calls, enhanced system prompt, flow awareness |
| `backend/agent/tools.py` | Modify | Bulk tool creation from OpenAPI, tool grouping |
| `backend/routers/tools.py` | Modify | Add bulk import endpoint |
| `backend/routers/knowledge.py` | Modify | Add API doc import endpoint |
| `backend/models/site.py` | Modify | Add `api_spec_url` field |
| `backend/main.py` | Modify | Register new router |
| `dashboard/src/pages/Tools.tsx` | Modify | Add "Import from OpenAPI" button + flow UI |
| `dashboard/src/lib/api.ts` | Modify | Add new API calls |

---

### Task 1: Fix Streaming Tool Calling (Critical Bug)

**Files:**
- Modify: `backend/agent/core.py:159-183`
- Modify: `backend/routers/chat.py:145-191`

This is the most critical fix. Currently the widget uses `stream_response()` which **completely ignores tool calls**. The bot can never execute API actions for end users.

- [ ] **Step 1: Add tool-aware streaming to ChatAgent**

Replace the current `stream_response` method with one that detects tool calls, executes them, and continues streaming:

```python
# In backend/agent/core.py — replace stream_response method entirely

async def stream_response(
    self,
    message: str,
    page_context: Optional[dict] = None,
    repos=None,
    visitor_id: Optional[str] = None,
    conversation_summary: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Process user message → stream response with tool calling support."""
    self.messages.append({"role": "user", "content": message})

    system_prompt, tools = await self._build_system_prompt(
        message, page_context, repos, visitor_id, conversation_summary,
    )

    max_tool_rounds = 3
    round_count = 0

    while True:
        # Use non-streaming chat when tools are available to detect tool calls
        if tools and round_count < max_tool_rounds:
            result = await self.provider.chat(
                messages=self.messages,
                system_prompt=system_prompt,
                tools=tools,
            )

            if result.get("tool_calls"):
                round_count += 1
                for tc in result["tool_calls"]:
                    # Notify user about tool execution
                    tool_msg = f"\n\n> Executing **{tc['name']}**...\n\n"
                    yield tool_msg

                    tool_meta = next(
                        (t["_meta"] for t in tools if t["name"] == tc["name"]), None
                    )
                    if tool_meta:
                        tool_result = await tool_executor.execute_tool(
                            tool_meta, tc["arguments"]
                        )
                        self.messages.append({
                            "role": "assistant",
                            "content": f"Calling tool: {tc['name']}({json.dumps(tc['arguments'], ensure_ascii=False)})",
                        })
                        self.messages.append({
                            "role": "user",
                            "content": f"Tool result for {tc['name']}: {json.dumps(tool_result, ensure_ascii=False)}",
                        })
                continue  # Loop back to get LLM response after tool execution

        # Stream the final text response
        full_response = ""
        async for token in self.provider.stream(
            messages=self.messages,
            system_prompt=system_prompt,
            tools=None,  # No tools for final streaming — already handled above
        ):
            full_response += token
            yield token
        break

    self.messages.append({"role": "assistant", "content": full_response})
```

- [ ] **Step 2: Run backend to verify no import errors**

Run: `cd backend && python -c "from agent.core import ChatAgent; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/agent/core.py
git commit -m "fix: enable tool calling during streaming responses"
```

---

### Task 2: Fix Embedding Provider Mismatch

**Files:**
- Modify: `backend/agent/core.py:106-108`

- [ ] **Step 1: Use configured embedding provider instead of hardcoded OpenAI**

Replace lines 106-108 in `core.py`:

```python
# OLD (hardcoded):
# embedding_provider = get_llm_provider("openai")

# NEW (use configured provider):
embedding_provider = get_llm_provider(
    settings.embedding_provider,
    settings.embedding_model,
)
```

Add `from config import settings` to imports if not already present.

- [ ] **Step 2: Verify import**

Run: `cd backend && python -c "from agent.core import ChatAgent; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/agent/core.py
git commit -m "fix: use configured embedding provider for query embeddings"
```

---

### Task 3: OpenAPI/Swagger Spec Parser

**Files:**
- Create: `backend/knowledge/openapi_parser.py`

This is the core of "learning API docs". Parse an OpenAPI 3.x or Swagger 2.x spec and extract:
- Endpoints → auto-create Tool records
- Descriptions → structured knowledge chunks
- Auth schemes → auto-configure tool auth
- Request/response schemas → parameter documentation

- [ ] **Step 1: Create the OpenAPI parser**

```python
"""OpenAPI/Swagger spec parser — extracts tools and knowledge from API specs."""

import json
import uuid
import hashlib
from typing import Optional
import httpx
import yaml


class OpenAPIParser:
    """Parse OpenAPI 3.x / Swagger 2.x specs into tools and knowledge chunks."""

    def __init__(self, spec: dict):
        self.spec = spec
        self.is_v3 = spec.get("openapi", "").startswith("3.")
        self.base_url = self._extract_base_url()
        self.auth_schemes = self._extract_auth_schemes()

    @classmethod
    async def from_url(cls, url: str) -> "OpenAPIParser":
        """Fetch and parse an OpenAPI spec from a URL."""
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "yaml" in content_type or "yml" in content_type or url.endswith((".yaml", ".yml")):
                spec = yaml.safe_load(resp.text)
            else:
                spec = resp.json()
        return cls(spec)

    @classmethod
    def from_text(cls, text: str, format: str = "auto") -> "OpenAPIParser":
        """Parse an OpenAPI spec from raw text."""
        if format == "yaml" or (format == "auto" and not text.strip().startswith("{")):
            spec = yaml.safe_load(text)
        else:
            spec = json.loads(text)
        return cls(spec)

    def _extract_base_url(self) -> str:
        if self.is_v3:
            servers = self.spec.get("servers", [])
            return servers[0]["url"] if servers else ""
        else:
            # Swagger 2.x
            host = self.spec.get("host", "")
            base_path = self.spec.get("basePath", "")
            schemes = self.spec.get("schemes", ["https"])
            return f"{schemes[0]}://{host}{base_path}" if host else ""

    def _extract_auth_schemes(self) -> dict:
        if self.is_v3:
            components = self.spec.get("components", {})
            return components.get("securitySchemes", {})
        else:
            return self.spec.get("securityDefinitions", {})

    def _resolve_ref(self, ref: str) -> dict:
        """Resolve a $ref pointer like '#/components/schemas/Pet'."""
        parts = ref.lstrip("#/").split("/")
        obj = self.spec
        for part in parts:
            obj = obj.get(part, {})
        return obj

    def _resolve_schema(self, schema: dict, depth: int = 0) -> dict:
        """Resolve schema references, with depth limit to avoid infinite recursion."""
        if depth > 5:
            return schema
        if "$ref" in schema:
            return self._resolve_schema(self._resolve_ref(schema["$ref"]), depth + 1)
        if schema.get("type") == "array" and "items" in schema:
            schema["items"] = self._resolve_schema(schema["items"], depth + 1)
        if "properties" in schema:
            for key, val in schema["properties"].items():
                schema["properties"][key] = self._resolve_schema(val, depth + 1)
        return schema

    def _schema_to_params(self, schema: dict) -> dict:
        """Convert a JSON Schema object to Plugo's params_schema format."""
        schema = self._resolve_schema(schema)
        params = {}
        properties = schema.get("properties", {})
        required_fields = schema.get("required", [])
        for name, prop in properties.items():
            params[name] = {
                "type": prop.get("type", "string"),
                "description": prop.get("description", ""),
                "required": name in required_fields,
            }
        return params

    def extract_tools(self, site_id: str) -> list[dict]:
        """Extract API endpoints as Plugo Tool records."""
        tools = []
        paths = self.spec.get("paths", {})

        for path, path_item in paths.items():
            for method in ("get", "post", "put", "delete", "patch"):
                operation = path_item.get(method)
                if not operation:
                    continue

                op_id = operation.get("operationId", f"{method}_{path}".replace("/", "_").strip("_"))
                summary = operation.get("summary", "")
                description = operation.get("description", summary)

                # Build params schema
                params_schema = {}

                # Query/path parameters
                parameters = operation.get("parameters", []) + path_item.get("parameters", [])
                for param in parameters:
                    if "$ref" in param:
                        param = self._resolve_ref(param["$ref"])
                    p_schema = param.get("schema", {})
                    if "$ref" in p_schema:
                        p_schema = self._resolve_ref(p_schema["$ref"])
                    params_schema[param["name"]] = {
                        "type": p_schema.get("type", "string"),
                        "description": param.get("description", ""),
                        "required": param.get("required", False),
                        "in": param.get("in", "query"),
                    }

                # Request body (OpenAPI 3.x)
                request_body = operation.get("requestBody", {})
                if request_body:
                    content = request_body.get("content", {})
                    json_content = content.get("application/json", {})
                    body_schema = json_content.get("schema", {})
                    if body_schema:
                        body_params = self._schema_to_params(body_schema)
                        params_schema.update(body_params)

                # Determine auth
                auth_type = None
                auth_value = None
                security = operation.get("security", self.spec.get("security", []))
                if security and self.auth_schemes:
                    first_scheme_name = list(security[0].keys())[0] if security[0] else None
                    if first_scheme_name:
                        scheme = self.auth_schemes.get(first_scheme_name, {})
                        scheme_type = scheme.get("type", "")
                        if scheme_type == "http" and scheme.get("scheme") == "bearer":
                            auth_type = "bearer"
                        elif scheme_type == "apiKey":
                            auth_type = "api_key"

                url = self.base_url.rstrip("/") + path

                tools.append({
                    "id": str(uuid.uuid4()),
                    "site_id": site_id,
                    "name": op_id,
                    "description": description or summary or f"{method.upper()} {path}",
                    "method": method.upper(),
                    "url": url,
                    "params_schema": params_schema,
                    "headers": {"Content-Type": "application/json"},
                    "auth_type": auth_type,
                    "auth_value": auth_value,
                    "enabled": True,
                })

        return tools

    def extract_knowledge_chunks(self, site_id: str) -> list[dict]:
        """Extract structured API documentation as knowledge chunks."""
        chunks = []
        info = self.spec.get("info", {})
        api_title = info.get("title", "API")
        api_description = info.get("description", "")

        # Chunk 1: API Overview
        if api_description:
            overview = f"# {api_title}\n\n{api_description}"
            if self.base_url:
                overview += f"\n\nBase URL: {self.base_url}"
            if info.get("version"):
                overview += f"\nVersion: {info['version']}"
            chunks.append(self._make_chunk(
                overview, f"{api_title} - Overview", self.base_url,
                site_id, 0, "API Overview", "API > Overview",
            ))

        # Chunk 2: Authentication
        if self.auth_schemes:
            auth_parts = [f"# {api_title} - Authentication\n"]
            for name, scheme in self.auth_schemes.items():
                auth_parts.append(f"## {name}")
                auth_parts.append(f"Type: {scheme.get('type', 'unknown')}")
                if scheme.get("scheme"):
                    auth_parts.append(f"Scheme: {scheme['scheme']}")
                if scheme.get("in"):
                    auth_parts.append(f"Location: {scheme['in']}")
                if scheme.get("name"):
                    auth_parts.append(f"Parameter name: {scheme['name']}")
                if scheme.get("description"):
                    auth_parts.append(scheme["description"])
                auth_parts.append("")
            chunks.append(self._make_chunk(
                "\n".join(auth_parts), f"{api_title} - Authentication",
                self.base_url, site_id, 1, "Authentication", "API > Authentication",
            ))

        # Chunks per endpoint group (by tag or path prefix)
        paths = self.spec.get("paths", {})
        chunk_index = 2
        for path, path_item in paths.items():
            for method_name in ("get", "post", "put", "delete", "patch"):
                operation = path_item.get(method_name)
                if not operation:
                    continue

                parts = [f"## {method_name.upper()} {path}"]
                if operation.get("summary"):
                    parts.append(f"**{operation['summary']}**")
                if operation.get("description"):
                    parts.append(operation["description"])

                # Parameters
                parameters = operation.get("parameters", [])
                if parameters:
                    parts.append("\n### Parameters")
                    for param in parameters:
                        if "$ref" in param:
                            param = self._resolve_ref(param["$ref"])
                        req = " (required)" if param.get("required") else " (optional)"
                        p_schema = param.get("schema", {})
                        p_type = p_schema.get("type", "string")
                        parts.append(
                            f"- `{param['name']}` ({p_type}, in {param.get('in', 'query')}){req}: "
                            f"{param.get('description', '')}"
                        )

                # Request body
                request_body = operation.get("requestBody", {})
                if request_body:
                    parts.append("\n### Request Body")
                    content = request_body.get("content", {})
                    json_content = content.get("application/json", {})
                    body_schema = json_content.get("schema", {})
                    if body_schema:
                        resolved = self._resolve_schema(dict(body_schema))
                        props = resolved.get("properties", {})
                        req_fields = resolved.get("required", [])
                        for pname, pval in props.items():
                            req = " (required)" if pname in req_fields else " (optional)"
                            parts.append(
                                f"- `{pname}` ({pval.get('type', 'any')}){req}: "
                                f"{pval.get('description', '')}"
                            )

                # Responses
                responses = operation.get("responses", {})
                if responses:
                    parts.append("\n### Responses")
                    for status_code, resp_obj in responses.items():
                        parts.append(f"- **{status_code}**: {resp_obj.get('description', '')}")

                endpoint_text = "\n".join(parts)
                tags = operation.get("tags", ["General"])
                section_path = f"API > {tags[0]} > {method_name.upper()} {path}"

                chunks.append(self._make_chunk(
                    endpoint_text,
                    f"{api_title} - {method_name.upper()} {path}",
                    f"{self.base_url}{path}",
                    site_id, chunk_index,
                    f"{method_name.upper()} {path}",
                    section_path,
                ))
                chunk_index += 1

        return chunks

    def extract_flows(self, site_id: str) -> list[dict]:
        """Infer common API workflows from the spec structure.

        Groups related endpoints by tags and identifies CRUD patterns,
        auth flows, and multi-step processes.
        """
        flows = []
        paths = self.spec.get("paths", {})

        # Group operations by tag
        tag_ops: dict[str, list[dict]] = {}
        for path, path_item in paths.items():
            for method_name in ("get", "post", "put", "delete"):
                operation = path_item.get(method_name)
                if not operation:
                    continue
                tags = operation.get("tags", ["General"])
                for tag in tags:
                    if tag not in tag_ops:
                        tag_ops[tag] = []
                    tag_ops[tag].append({
                        "method": method_name.upper(),
                        "path": path,
                        "operation_id": operation.get("operationId", f"{method_name}_{path}"),
                        "summary": operation.get("summary", ""),
                        "description": operation.get("description", ""),
                    })

        # Build flows from tag groups
        for tag, ops in tag_ops.items():
            if len(ops) < 2:
                continue

            steps = []
            for i, op in enumerate(ops):
                steps.append({
                    "order": i + 1,
                    "action": f"{op['method']} {op['path']}",
                    "description": op["summary"] or op["description"] or f"{op['method']} {op['path']}",
                    "tool_name": op["operation_id"],
                })

            flows.append({
                "id": str(uuid.uuid4()),
                "site_id": site_id,
                "name": f"{tag} Operations",
                "description": f"Available operations for {tag}",
                "steps": steps,
                "trigger_phrases": [
                    f"how to use {tag.lower()}",
                    f"{tag.lower()} operations",
                    f"what can I do with {tag.lower()}",
                ],
            })

        return flows

    @staticmethod
    def _make_chunk(
        content: str, title: str, source_url: str, site_id: str,
        chunk_index: int, section_header: str, section_path: str,
    ) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "site_id": site_id,
            "source_url": source_url,
            "title": title,
            "content": content,
            "chunk_index": chunk_index,
            "content_hash": hashlib.sha256(content.encode()).hexdigest(),
            "section_header": section_header,
            "section_path": section_path,
            "word_count": len(content.split()),
            "source_type": "api_spec",
        }
```

- [ ] **Step 2: Install pyyaml dependency**

Run: `cd backend && pip install pyyaml`

Also add `pyyaml` to `requirements.txt` or `pyproject.toml`.

- [ ] **Step 3: Verify import**

Run: `cd backend && python -c "from knowledge.openapi_parser import OpenAPIParser; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/knowledge/openapi_parser.py
git commit -m "feat: add OpenAPI/Swagger spec parser for auto-generating tools and knowledge"
```

---

### Task 4: Flow/Workflow Data Model

**Files:**
- Create: `backend/models/flow.py`

- [ ] **Step 1: Create the Flow model**

```python
"""Flow model — multi-step workflows the bot can guide users through."""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Boolean, Integer, ForeignKey, JSON
from database import Base


class Flow(Base):
    __tablename__ = "flows"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id = Column(String, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    steps = Column(JSON, default=list)  # [{order, action, description, tool_name?, expected_input?, expected_output?}]
    trigger_phrases = Column(JSON, default=list)  # Phrases that should activate this flow

    enabled = Column(Boolean, default=True)
    source = Column(String(50), default="manual")  # manual | api_spec | crawl
    created_at = Column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 2: Register model in `backend/models/__init__.py`**

Add import: `from models.flow import Flow`

- [ ] **Step 3: Add `api_spec_url` to Site model**

In `backend/models/site.py`, add after line 28 (`allowed_domains`):

```python
# API spec
api_spec_url = Column(String(2048), nullable=True)  # OpenAPI/Swagger spec URL
```

- [ ] **Step 4: Commit**

```bash
git add backend/models/flow.py backend/models/__init__.py backend/models/site.py
git commit -m "feat: add Flow model and api_spec_url to Site"
```

---

### Task 5: Flow Repository

**Files:**
- Modify: `backend/repositories/base.py`
- Modify: `backend/repositories/sqlite_repo.py`
- Modify: `backend/repositories/__init__.py`

- [ ] **Step 1: Add FlowRepository abstract base**

In `backend/repositories/base.py`, add:

```python
class BaseFlowRepository(ABC):
    @abstractmethod
    async def create(self, data: dict) -> dict: ...
    @abstractmethod
    async def create_many(self, flows: list[dict]) -> int: ...
    @abstractmethod
    async def list_by_site(self, site_id: str) -> list[dict]: ...
    @abstractmethod
    async def get_by_id(self, flow_id: str) -> Optional[dict]: ...
    @abstractmethod
    async def update(self, flow_id: str, data: dict) -> Optional[dict]: ...
    @abstractmethod
    async def delete(self, flow_id: str) -> bool: ...
    @abstractmethod
    async def delete_by_site(self, site_id: str) -> int: ...
```

- [ ] **Step 2: Add SQLite flow repository implementation**

In `backend/repositories/sqlite_repo.py`, add:

```python
from models.flow import Flow

class SQLiteFlowRepository(BaseFlowRepository):
    def __init__(self, session):
        self.session = session

    async def create(self, data: dict) -> dict:
        flow = Flow(**data)
        self.session.add(flow)
        await self.session.flush()
        return self._to_dict(flow)

    async def create_many(self, flows: list[dict]) -> int:
        count = 0
        for data in flows:
            flow = Flow(**data)
            self.session.add(flow)
            count += 1
        await self.session.flush()
        return count

    async def list_by_site(self, site_id: str) -> list[dict]:
        result = await self.session.execute(
            select(Flow).where(Flow.site_id == site_id).order_by(Flow.created_at)
        )
        return [self._to_dict(f) for f in result.scalars().all()]

    async def get_by_id(self, flow_id: str) -> Optional[dict]:
        result = await self.session.execute(select(Flow).where(Flow.id == flow_id))
        flow = result.scalar_one_or_none()
        return self._to_dict(flow) if flow else None

    async def update(self, flow_id: str, data: dict) -> Optional[dict]:
        result = await self.session.execute(select(Flow).where(Flow.id == flow_id))
        flow = result.scalar_one_or_none()
        if not flow:
            return None
        for key, value in data.items():
            setattr(flow, key, value)
        await self.session.flush()
        return self._to_dict(flow)

    async def delete(self, flow_id: str) -> bool:
        result = await self.session.execute(select(Flow).where(Flow.id == flow_id))
        flow = result.scalar_one_or_none()
        if not flow:
            return False
        await self.session.delete(flow)
        await self.session.flush()
        return True

    async def delete_by_site(self, site_id: str) -> int:
        result = await self.session.execute(select(Flow).where(Flow.site_id == site_id))
        flows = result.scalars().all()
        for flow in flows:
            await self.session.delete(flow)
        await self.session.flush()
        return len(flows)

    @staticmethod
    def _to_dict(flow: Flow) -> dict:
        return {
            "id": flow.id,
            "site_id": flow.site_id,
            "name": flow.name,
            "description": flow.description,
            "steps": flow.steps,
            "trigger_phrases": flow.trigger_phrases,
            "enabled": flow.enabled,
            "source": flow.source,
            "created_at": flow.created_at.isoformat() if flow.created_at else None,
        }
```

- [ ] **Step 3: Wire into Repositories**

In `backend/repositories/__init__.py`, add `flows: SQLiteFlowRepository` to the `Repositories` dataclass and instantiate it in `get_repos()`.

- [ ] **Step 4: Commit**

```bash
git add backend/repositories/base.py backend/repositories/sqlite_repo.py backend/repositories/__init__.py
git commit -m "feat: add Flow repository with SQLite implementation"
```

---

### Task 6: API Import Router

**Files:**
- Create: `backend/routers/api_import.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Create the API import router**

```python
"""API Import router — import OpenAPI specs to auto-generate tools, knowledge, and flows."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from typing import Optional
from repositories import get_repos, Repositories
from knowledge.openapi_parser import OpenAPIParser
from agent.rag import rag_engine
from providers.factory import get_llm_provider
from config import settings
from auth import get_current_user, TokenData
from logging_config import logger

router = APIRouter(prefix="/api/import", tags=["api-import"])


class ImportFromURLRequest(BaseModel):
    site_id: str
    spec_url: str
    import_tools: bool = True
    import_knowledge: bool = True
    import_flows: bool = True
    auth_type: Optional[str] = None  # Override auth for all imported tools
    auth_value: Optional[str] = None


class ImportFromTextRequest(BaseModel):
    site_id: str
    spec_text: str
    format: str = "auto"  # auto | json | yaml
    import_tools: bool = True
    import_knowledge: bool = True
    import_flows: bool = True
    auth_type: Optional[str] = None
    auth_value: Optional[str] = None


@router.post("/openapi/url")
async def import_from_url(
    data: ImportFromURLRequest,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Import an OpenAPI spec from a URL."""
    try:
        parser = await OpenAPIParser.from_url(data.spec_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch/parse spec: {str(e)}")

    return await _process_import(parser, data.site_id, data, repos)


@router.post("/openapi/text")
async def import_from_text(
    data: ImportFromTextRequest,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Import an OpenAPI spec from raw text."""
    try:
        parser = OpenAPIParser.from_text(data.spec_text, data.format)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse spec: {str(e)}")

    return await _process_import(parser, data.site_id, data, repos)


@router.post("/openapi/file")
async def import_from_file(
    site_id: str,
    file: UploadFile = File(...),
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    """Import an OpenAPI spec from an uploaded file."""
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")

    try:
        fmt = "yaml" if file.filename and file.filename.endswith((".yaml", ".yml")) else "auto"
        parser = OpenAPIParser.from_text(text, fmt)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse spec: {str(e)}")

    # Use a simple config object for the import
    class ImportConfig:
        import_tools = True
        import_knowledge = True
        import_flows = True
        auth_type = None
        auth_value = None

    return await _process_import(parser, site_id, ImportConfig(), repos)


async def _process_import(parser: OpenAPIParser, site_id: str, config, repos) -> dict:
    """Process a parsed OpenAPI spec: create tools, knowledge, and flows."""
    result = {"tools_created": 0, "knowledge_chunks": 0, "flows_created": 0}

    # Import tools
    if config.import_tools:
        tools = parser.extract_tools(site_id)
        for tool in tools:
            # Override auth if provided
            if config.auth_type:
                tool["auth_type"] = config.auth_type
            if config.auth_value:
                tool["auth_value"] = config.auth_value
            await repos.tools.create(tool)
        result["tools_created"] = len(tools)

    # Import knowledge chunks
    if config.import_knowledge:
        chunks = parser.extract_knowledge_chunks(site_id)
        if chunks:
            # Embed and store
            try:
                embed_provider = get_llm_provider(
                    settings.embedding_provider, settings.embedding_model
                )
                contents = [c["content"] for c in chunks]
                embeddings = await embed_provider.embed(contents)
                await rag_engine.add_chunks(site_id, chunks, embeddings)
            except Exception as e:
                logger.warning("Failed to embed API knowledge chunks", error=str(e))

            for chunk in chunks:
                chunk["embedding_id"] = chunk["id"]
            await repos.knowledge.create_many(chunks)
            result["knowledge_chunks"] = len(chunks)

    # Import flows
    if config.import_flows:
        flows = parser.extract_flows(site_id)
        for flow in flows:
            await repos.flows.create(flow)
        result["flows_created"] = len(flows)

    # Update site with spec URL if available
    if hasattr(config, "spec_url") and config.spec_url:
        await repos.sites.update(site_id, {"api_spec_url": config.spec_url})

    return result
```

- [ ] **Step 2: Register router in main.py**

In `backend/main.py`, add:

```python
from routers.api_import import router as api_import_router
app.include_router(api_import_router)
```

- [ ] **Step 3: Verify startup**

Run: `cd backend && python -c "from routers.api_import import router; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/routers/api_import.py backend/main.py
git commit -m "feat: add API import router for OpenAPI spec ingestion"
```

---

### Task 7: Enhanced System Prompt with Flow Awareness

**Files:**
- Modify: `backend/agent/core.py`

- [ ] **Step 1: Update system prompt template**

Replace `SYSTEM_PROMPT_TEMPLATE` in `core.py`:

```python
SYSTEM_PROMPT_TEMPLATE = """You are an AI assistant for the website "{site_name}" ({site_url}).

## Your Role
You operate in three modes:

### 1. Knowledge Mode (Guidance)
Based on content crawled from the website and API documentation, you help users by:
- Answering questions about the website, products, services, and API capabilities
- Providing step-by-step instructions for using the website or its APIs
- Explaining how different features work together (flows/workflows)
- Delivering accurate information from the knowledge base
- If no relevant information is found, clearly state so and suggest alternatives

### 2. Action Mode (Execute on behalf)
When API tools are available, you perform actions for the user:
- Search products, place orders, register accounts, query data
- Fill forms, look up information, create/update resources
- Chain multiple API calls when a task requires several steps
- ALWAYS explain the action before executing it
- ALWAYS ask for confirmation before performing critical actions (delete, payment, etc.)
- After executing, summarize the result clearly

### 3. Flow Mode (Guided Workflows)
When workflows are defined, you guide users through multi-step processes:
- Identify when a user's intent matches a known flow
- Walk them through each step, explaining what happens
- Execute API calls at each step when tools are available
- Track progress and handle errors at each step

## Rules
- Respond in the same language the user is using
- Prioritize answering from the knowledge base and API docs first
- If a suitable tool exists for the user's request, suggest and use it
- When guiding through a flow, number the steps and indicate progress
- Keep responses concise and friendly
- For API-related questions, include relevant endpoint details and examples

{memory_section}

{context_section}

{knowledge_section}

{flows_section}

{tools_section}
"""
```

- [ ] **Step 2: Add flow section builder to `_build_system_prompt`**

Add flow loading after the tools section in `_build_system_prompt`:

```python
# --- Flows (guided workflows) ---
flows_section = ""
if repos:
    try:
        flows = await repos.flows.list_by_site(self.site_id)
        enabled_flows = [f for f in flows if f.get("enabled", True)]
        if enabled_flows:
            flow_parts = []
            for flow in enabled_flows:
                steps_text = "\n".join(
                    f"  {s['order']}. {s['description']}"
                    for s in flow.get("steps", [])
                )
                triggers = ", ".join(flow.get("trigger_phrases", []))
                flow_parts.append(
                    f"### {flow['name']}\n{flow.get('description', '')}\n"
                    f"Triggers: {triggers}\nSteps:\n{steps_text}"
                )
            flows_section = (
                "## Available Workflows\n"
                "When the user's intent matches a workflow, guide them through the steps.\n\n"
                + "\n\n".join(flow_parts)
            )
    except Exception:
        pass
```

Update the `prompt = SYSTEM_PROMPT_TEMPLATE.format(...)` call to include `flows_section=flows_section`.

- [ ] **Step 3: Commit**

```bash
git add backend/agent/core.py
git commit -m "feat: enhance system prompt with flow awareness and API knowledge modes"
```

---

### Task 8: Dashboard — OpenAPI Import UI

**Files:**
- Modify: `dashboard/src/pages/Tools.tsx`
- Modify: `dashboard/src/lib/api.ts`

- [ ] **Step 1: Add API import functions to `dashboard/src/lib/api.ts`**

```typescript
export const importOpenAPIFromURL = (data: {
  site_id: string;
  spec_url: string;
  auth_type?: string;
  auth_value?: string;
}) => api.post("/import/openapi/url", data).then((r) => r.data);

export const importOpenAPIFromText = (data: {
  site_id: string;
  spec_text: string;
  format?: string;
}) => api.post("/import/openapi/text", data).then((r) => r.data);

export const importOpenAPIFromFile = (siteId: string, file: File) => {
  const formData = new FormData();
  formData.append("file", file);
  return api.post(`/import/openapi/file?site_id=${siteId}`, formData).then((r) => r.data);
};

export const getFlows = (siteId: string) =>
  api.get(`/flows?site_id=${siteId}`).then((r) => r.data);

export const deleteFlow = (flowId: string) =>
  api.delete(`/flows/${flowId}`).then((r) => r.data);
```

- [ ] **Step 2: Add OpenAPI import section to Tools.tsx**

Add an import modal/section before the tools list. Add a new state `showImport` and a form with:
- URL input field for spec URL
- OR file upload for spec file
- OR textarea for raw spec text
- Auth type/value override fields
- Import button that calls `importOpenAPIFromURL` / `importOpenAPIFromFile` / `importOpenAPIFromText`
- Show results: `{tools_created} tools, {knowledge_chunks} knowledge chunks, {flows_created} flows imported`

```tsx
// Add to imports
import { importOpenAPIFromURL, importOpenAPIFromFile } from "../lib/api";
import { Download } from "lucide-react";

// Add state
const [showImport, setShowImport] = useState(false);
const [importUrl, setImportUrl] = useState("");
const [importAuth, setImportAuth] = useState({ type: "none", value: "" });

const importMutation = useMutation({
  mutationFn: async () => {
    if (!siteId || !importUrl) return;
    return importOpenAPIFromURL({
      site_id: siteId,
      spec_url: importUrl,
      auth_type: importAuth.type === "none" ? undefined : importAuth.type,
      auth_value: importAuth.value || undefined,
    });
  },
  onSuccess: (data) => {
    queryClient.invalidateQueries({ queryKey: ["tools", siteId] });
    setShowImport(false);
    setImportUrl("");
    toast.success(
      `Imported: ${data.tools_created} tools, ${data.knowledge_chunks} knowledge chunks, ${data.flows_created} flows`
    );
  },
  onError: () => toast.error("Failed to import API spec"),
});

const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
  const file = e.target.files?.[0];
  if (!file || !siteId) return;
  try {
    const result = await importOpenAPIFromFile(siteId, file);
    queryClient.invalidateQueries({ queryKey: ["tools", siteId] });
    toast.success(
      `Imported: ${result.tools_created} tools, ${result.knowledge_chunks} knowledge chunks, ${result.flows_created} flows`
    );
  } catch {
    toast.error("Failed to import API spec");
  }
};

// Add to JSX — next to "Add Tool" button:
<button
  onClick={() => setShowImport(true)}
  className="flex items-center gap-2 bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-50"
>
  <Download className="w-4 h-4" /> Import from OpenAPI
</button>

// Import form (render when showImport is true):
{showImport && (
  <div className="bg-white p-6 rounded-xl border border-gray-200 mb-6">
    <h3 className="font-semibold mb-4">Import from OpenAPI / Swagger</h3>
    <p className="text-sm text-gray-500 mb-4">
      Paste a URL to your OpenAPI spec (JSON/YAML) or upload a file. This will auto-create tools, knowledge chunks, and workflows.
    </p>
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Spec URL</label>
        <input
          value={importUrl}
          onChange={(e) => setImportUrl(e.target.value)}
          placeholder="https://api.example.com/openapi.json"
          className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>
      <div className="flex items-center gap-3 text-sm text-gray-500">
        <span>or</span>
        <label className="flex items-center gap-2 bg-gray-50 border border-gray-200 px-3 py-1.5 rounded-lg cursor-pointer hover:bg-gray-100">
          Upload file (.json, .yaml)
          <input type="file" accept=".json,.yaml,.yml" onChange={handleImportFile} className="hidden" />
        </label>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Auth Type (for all endpoints)</label>
          <select
            value={importAuth.type}
            onChange={(e) => setImportAuth({ ...importAuth, type: e.target.value })}
            className="w-full border rounded-lg px-3 py-2 outline-none"
          >
            <option value="none">Auto-detect from spec</option>
            <option value="bearer">Bearer Token</option>
            <option value="api_key">API Key</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Auth Value</label>
          <input
            value={importAuth.value}
            onChange={(e) => setImportAuth({ ...importAuth, value: e.target.value })}
            placeholder="Token or key..."
            type="password"
            className="w-full border rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
      </div>
    </div>
    <div className="flex gap-3 mt-4">
      <button
        onClick={() => importMutation.mutate()}
        disabled={importMutation.isPending || !importUrl}
        className="bg-primary-600 text-white px-4 py-2 rounded-lg disabled:opacity-50"
      >
        {importMutation.isPending ? "Importing..." : "Import"}
      </button>
      <button onClick={() => setShowImport(false)} className="text-gray-500 px-4 py-2">Cancel</button>
    </div>
  </div>
)}
```

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/pages/Tools.tsx dashboard/src/lib/api.ts
git commit -m "feat: add OpenAPI import UI to dashboard Tools page"
```

---

### Task 9: Flow Management Router + UI

**Files:**
- Create: `backend/routers/flows.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Create flows router**

```python
"""Flow management router."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from repositories import get_repos, Repositories
from auth import get_current_user, TokenData

router = APIRouter(prefix="/api/flows", tags=["flows"])


class FlowCreate(BaseModel):
    site_id: str
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    steps: list[dict] = Field(default_factory=list)
    trigger_phrases: list[str] = Field(default_factory=list)


class FlowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[list[dict]] = None
    trigger_phrases: Optional[list[str]] = None
    enabled: Optional[bool] = None


@router.get("")
async def list_flows(
    site_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    return await repos.flows.list_by_site(site_id)


@router.post("")
async def create_flow(
    data: FlowCreate,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    flow = await repos.flows.create(data.model_dump())
    return {"id": flow["id"], "message": "Flow created"}


@router.put("/{flow_id}")
async def update_flow(
    flow_id: str,
    data: FlowUpdate,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    flow = await repos.flows.update(flow_id, data.model_dump(exclude_none=True))
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return {"message": "Flow updated"}


@router.delete("/{flow_id}")
async def delete_flow(
    flow_id: str,
    repos: Repositories = Depends(get_repos),
    _user: TokenData = Depends(get_current_user),
):
    ok = await repos.flows.delete(flow_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Flow not found")
    return {"message": "Flow deleted"}
```

- [ ] **Step 2: Register in main.py**

```python
from routers.flows import router as flows_router
app.include_router(flows_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/routers/flows.py backend/main.py
git commit -m "feat: add Flow CRUD router"
```

---

### Task 10: Database Migration — Create New Tables

**Files:**
- Modify: `backend/main.py` (lifespan creates tables)

- [ ] **Step 1: Ensure new models are imported before `create_all`**

Verify that `backend/main.py`'s lifespan function calls `Base.metadata.create_all()` and that all new models (Flow) are imported before that point. If the project uses Alembic, create a migration instead.

- [ ] **Step 2: Test table creation**

Run: `cd backend && python -c "from database import engine, Base; from models import *; import asyncio; asyncio.run(Base.metadata.create_all(engine))"`

Or just start the backend and check that no errors occur.

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "chore: ensure new Flow table is created on startup"
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - [x] Learn API docs → Task 3 (OpenAPI parser) + Task 6 (import router)
   - [x] Operate through APIs → Task 1 (streaming tool calling fix)
   - [x] Learn flows → Task 4 (Flow model) + Task 7 (flow-aware prompt) + Task 9 (flow router)
   - [x] Learn project functionalities → Task 3 (knowledge chunks from API spec) + Task 7 (enhanced prompt)

2. **Placeholder scan:** No TBD/TODO found. All code blocks are complete.

3. **Type consistency:** `OpenAPIParser` methods return `list[dict]` matching repo input types. `Flow` model fields match router Pydantic models. `_process_import` wires parser output to repos correctly.

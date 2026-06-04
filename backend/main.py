import hmac
import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

load_dotenv()

import models  # noqa: F401 — ensure all models registered for Base.metadata.create_all
from auth import CSRF_COOKIE, SESSION_COOKIE
from config import settings, validate_settings

# --- Rate limiter ---
# The instance lives in `limiter.py` so routers can apply `@limiter.limit(...)`
# at import time without a circular import (main.py imports routers above).
# Admin endpoints: per-IP (authenticated, so IPs are meaningful).
# Public endpoints: per-site-token (isolate tenants), via utils.rate_limit.
from limiter import limiter
from logging_config import logger
from routers import analytics, chat, crawl, flows, knowledge, memory, sessions, sites, tools
from routers import audit as audit_router
from routers import auth as auth_router
from routers import chat_sse as chat_sse_router
from routers import config as config_router
from routers import llm_keys as llm_keys_router
from routers import models as models_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — validate settings and initialize database
    validate_settings()
    os.makedirs("data", exist_ok=True)

    if settings.database_provider == "sqlite":
        from database import init_db

        await init_db()
        logger.info("Database initialized", provider="sqlite", url=settings.database_url)
    else:
        from repositories import _get_mongo_db
        from repositories.mongo_repo import ensure_indexes

        db = _get_mongo_db()
        await ensure_indexes(db)
        logger.info(
            "Database initialized", provider="mongodb", url=f"{settings.mongodb_url}/{settings.mongodb_database}"
        )

    logger.info(
        "Plugo Backend started",
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        auth_enabled=settings.auth_enabled,
    )

    # Clean up orphaned "running" crawls from previous process
    from routers.crawl import cleanup_stale_crawls_on_startup

    await cleanup_stale_crawls_on_startup()

    # Start auto-crawl scheduler
    from scheduler import start_scheduler, stop_scheduler

    start_scheduler()

    yield

    # Shutdown — stop scheduler and close database connections
    await stop_scheduler()
    if settings.database_provider == "mongodb":
        from repositories import close_mongo

        await close_mongo()
    logger.info("Plugo Backend shutting down")


app = FastAPI(
    title="Plugo",
    description="Embeddable AI Chat Widget - Backend API",
    version="1.0.0",
    lifespan=lifespan,
)

# --- Rate limiter middleware ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS ---
# Global allowlist — coarse gate for the admin dashboard and anything not
# tied to a specific tenant. Multi-tenant isolation for public widget routes
# lives in `utils/cors.py::validate_site_origin` because this middleware
# can't see which `site_token` a request targets.
origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# --- CSRF protection (double-submit) ---
# Only cookie-authenticated requests are CSRF-able: a Bearer Authorization header
# isn't auto-attached by the browser cross-site, so header-auth API clients and
# the widget (site-token bearer) need no CSRF token. For unsafe methods carrying
# the session cookie without an Authorization header, require X-CSRF-Token to
# match the CSRF cookie.
_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
# login bootstraps the session; logout only clears cookies (never harmful) and
# must stay reachable even if the CSRF cookie was lost but the session cookie wasn't.
_CSRF_EXEMPT_PATHS = {"/api/auth/login", "/api/auth/logout"}


@app.middleware("http")
async def csrf_protect(request: Request, call_next):
    if request.method not in _CSRF_SAFE_METHODS and request.url.path not in _CSRF_EXEMPT_PATHS:
        session_cookie = request.cookies.get(SESSION_COOKIE)
        has_auth_header = request.headers.get("authorization")
        if session_cookie and not has_auth_header:
            csrf_cookie = request.cookies.get(CSRF_COOKIE)
            csrf_header = request.headers.get("x-csrf-token")
            if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
                return JSONResponse(status_code=403, content={"detail": "CSRF token missing or invalid"})
    return await call_next(request)


# --- Security headers + request ID middleware ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    # Per-request ID for log correlation; echoed back so clients/ops can quote it
    # when reporting an error.
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    logger.debug("Request", method=request.method, path=request.url.path, request_id=request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# --- Global exception handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.error("Unhandled exception", error=str(exc), path=request.url.path, request_id=request_id)
    return JSONResponse(
        status_code=500,
        headers={"X-Request-ID": request_id} if request_id else None,
        content={
            "detail": "An internal error occurred. Please try again later.",
            "request_id": request_id,
        },
    )


# --- Static files for widget ---
widget_paths = [
    "/app/static_widget",  # Docker: shared volume
    os.path.join(os.path.dirname(__file__), "..", "frontend", "widget-dist"),  # Local dev
]
for widget_dir in widget_paths:
    if os.path.exists(widget_dir):
        app.mount("/static", StaticFiles(directory=widget_dir), name="static")
        break

# --- Routers ---
app.include_router(auth_router.router)
app.include_router(chat.router)
app.include_router(sites.router)
app.include_router(crawl.router)
app.include_router(knowledge.router)
app.include_router(tools.router)
app.include_router(sessions.router)
app.include_router(memory.router)
app.include_router(analytics.router)
app.include_router(audit_router.router)
app.include_router(llm_keys_router.router)
app.include_router(models_router.router)
app.include_router(config_router.router)
app.include_router(flows.router)
app.include_router(chat_sse_router.register_routes())


@app.get("/")
async def root():
    return {
        "name": "Plugo",
        "version": "1.0.0",
        "description": "Embeddable AI Chat Widget",
        "database": settings.database_provider,
        "auth_enabled": settings.auth_enabled,
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "database": settings.database_provider}

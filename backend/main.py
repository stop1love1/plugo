import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

load_dotenv()

import models  # noqa: F401 — ensure all models registered for Base.metadata.create_all
from config import settings, validate_settings
from logging_config import logger
from routers import analytics, chat, crawl, flows, knowledge, memory, sessions, sites, tools
from routers import audit as audit_router
from routers import auth as auth_router
from routers import config as config_router
from routers import llm_keys as llm_keys_router
from routers import models as models_router

# --- Rate limiter ---
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default])


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
        logger.info("Database initialized", provider="mongodb", url=f"{settings.mongodb_url}/{settings.mongodb_database}")

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
origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# --- Security headers middleware ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    logger.debug("Request", method=request.method, path=request.url.path)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# --- Global exception handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."},
    )

# --- Static files for widget ---
widget_paths = [
    "/app/static_widget",                                          # Docker: shared volume
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

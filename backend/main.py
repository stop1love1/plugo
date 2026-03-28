import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

from config import settings, validate_settings
from logging_config import logger
from routers import chat, sites, crawl, knowledge, tools, sessions, memory, analytics
from routers import auth as auth_router
from routers import users as users_router
from routers import audit as audit_router


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
        logger.info("Database initialized", provider="mongodb", url=f"{settings.mongodb_url}/{settings.mongodb_database}")

    logger.info(
        "Plugo Backend started",
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        auth_enabled=settings.auth_enabled,
    )
    yield

    # Shutdown — close database connections
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

# --- Request logging middleware ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.debug("Request", method=request.method, path=request.url.path)
    response = await call_next(request)
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
    os.path.join(os.path.dirname(__file__), "..", "widget", "dist"),  # Local dev
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
app.include_router(users_router.router)
app.include_router(audit_router.router)


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

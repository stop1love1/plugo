import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import json as _json
from html import escape as html_escape
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
from routers import llm_keys as llm_keys_router


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
app.include_router(llm_keys_router.router)


@app.get("/demo/{site_token}", response_class=HTMLResponse)
async def demo_page(site_token: str):
    """Serve a demo page with the widget embedded for testing."""
    from repositories import create_repos
    repos = await create_repos()
    try:
        site = await repos.sites.get_by_token(site_token)
    finally:
        await repos.close()
    if not site:
        return HTMLResponse("<h1>Site not found</h1>", status_code=404)

    # Escape values for safe HTML/JS injection
    safe_name = html_escape(site['name'] or '')
    safe_color = html_escape(site['primary_color'] or '#6366f1')
    js_token = _json.dumps(site['token'] or '')
    js_color = _json.dumps(site['primary_color'] or '#6366f1')
    js_greeting = _json.dumps(site['greeting'] or 'Hello! How can I help?')
    js_position = _json.dumps(site['position'] or 'bottom-right')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_name} — Plugo Demo</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f9fafb; color: #1e293b; }}
  .container {{ max-width: 900px; margin: 0 auto; padding: 24px; }}
  nav {{ display: flex; align-items: center; justify-content: space-between; padding: 16px 0; border-bottom: 1px solid #e2e8f0; margin-bottom: 40px; }}
  nav .brand {{ font-weight: 700; font-size: 1.25rem; color: {safe_color}; }}
  nav .links {{ display: flex; gap: 24px; font-size: 0.875rem; color: #64748b; }}
  nav .links a {{ color: inherit; text-decoration: none; }}
  .hero {{ text-align: center; padding: 60px 0; }}
  .hero h1 {{ font-size: 2.25rem; font-weight: 800; margin-bottom: 12px; }}
  .hero p {{ font-size: 1.05rem; color: #64748b; max-width: 500px; margin: 0 auto 28px; }}
  .hero .btn {{ display: inline-block; background: {safe_color}; color: #fff; padding: 12px 32px; border-radius: 8px; font-weight: 600; text-decoration: none; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin: 40px 0; }}
  .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px; }}
  .card h3 {{ font-size: 1rem; margin-bottom: 6px; }}
  .card p {{ font-size: 0.85rem; color: #64748b; }}
  .badge {{ display: inline-block; background: #dcfce7; color: #166534; font-size: 0.7rem; font-weight: 600; padding: 2px 8px; border-radius: 9999px; margin-left: 8px; }}
  footer {{ text-align: center; font-size: 0.8rem; color: #94a3b8; padding: 32px 0; border-top: 1px solid #e2e8f0; margin-top: 40px; }}
</style>
</head>
<body>
<div class="container">
  <nav>
    <div class="brand">{safe_name}</div>
    <div class="links">
      <a href="#">Home</a>
      <a href="#">Features</a>
      <a href="#">Pricing</a>
      <a href="#">Docs</a>
    </div>
  </nav>
  <div class="hero">
    <h1>Welcome to {safe_name}<span class="badge">Demo</span></h1>
    <p>This is a demo page to test the Plugo chat widget. Click the chat bubble to start a conversation!</p>
    <a href="#" class="btn">Get Started</a>
  </div>
  <div class="cards">
    <div class="card"><h3>AI Chat</h3><p>Chat with an AI assistant that knows about your website content.</p></div>
    <div class="card"><h3>Knowledge Base</h3><p>Powered by crawled content and your custom knowledge entries.</p></div>
    <div class="card"><h3>API Tools</h3><p>The bot can call your APIs to perform actions on behalf of visitors.</p></div>
  </div>
  <footer>Plugo Demo Page &mdash; This page is for testing only.</footer>
</div>
<script>
  window.PlugoConfig = {{
    token: {js_token},
    serverUrl: "ws://" + window.location.hostname + ":8000",
    primaryColor: {js_color},
    greeting: {js_greeting},
    position: {js_position}
  }};
</script>
<script src="/static/widget.js" async></script>
</body>
</html>"""
    return HTMLResponse(html)


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

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from config import settings
from routers import chat, sites, crawl, knowledge, tools, sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs("data", exist_ok=True)

    if settings.database_provider == "sqlite":
        from database import init_db
        await init_db()
        print(f"   Database: SQLite ({settings.database_url})")
    else:
        print(f"   Database: MongoDB ({settings.mongodb_url}/{settings.mongodb_database})")

    print("✅ Plugo Backend started")
    print(f"   LLM Provider: {settings.llm_provider}")
    print(f"   Model: {settings.llm_model}")
    yield

    # Shutdown
    if settings.database_provider == "mongodb":
        from repositories import close_mongo
        await close_mongo()
    print("👋 Plugo Backend shutting down")


app = FastAPI(
    title="Plugo",
    description="Embeddable AI Chat Widget - Backend API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for widget
widget_dir = os.path.join(os.path.dirname(__file__), "..", "widget", "dist")
if os.path.exists(widget_dir):
    app.mount("/static", StaticFiles(directory=widget_dir), name="static")

# Routers
app.include_router(chat.router)
app.include_router(sites.router)
app.include_router(crawl.router)
app.include_router(knowledge.router)
app.include_router(tools.router)
app.include_router(sessions.router)


@app.get("/")
async def root():
    return {
        "name": "Plugo",
        "version": "1.0.0",
        "description": "Embeddable AI Chat Widget",
        "database": settings.database_provider,
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "database": settings.database_provider}

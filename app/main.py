"""FastAPI application entry point for ADP.

Start with:
    uvicorn app.main:app --reload --port 8000

Swagger UI:  http://localhost:8000/docs
ReDoc:       http://localhost:8000/redoc
Health:      http://localhost:8000/health
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.evaluations import router as evaluations_router
from app.api.tasks import router as tasks_router
from app.api.webhooks import router as webhooks_router
from app.config import get_settings

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Technical Factory — ADP",
    description="AI-Powered SDLC Automation Platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — tighten origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else ["https://your-frontend.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(tasks_router)
app.include_router(evaluations_router)
app.include_router(webhooks_router)


@app.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env, "version": "0.1.0"}


@app.get("/health/models", tags=["system"])
async def health_models() -> dict:
    """Dry-run health check for all configured LLM models."""
    from app.agents.litellm_router import get_router
    router = get_router()
    results = await router.health_check()
    all_ok = all(v["status"] == "ok" for v in results.values())
    return {"all_ok": all_ok, "models": results}

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

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.evaluations import router as evaluations_router
from app.api.tasks import router as tasks_router
from app.api.webhooks import router as webhooks_router
from app.config import get_settings
from app.middleware.rate_limiter import RateLimitMiddleware, RateLimitStore

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


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    status_code = 400 if request.url.path.startswith("/auth/") else 422
    return JSONResponse(
        status_code=status_code,
        content={"detail": jsonable_encoder(exc.errors())},
    )

# CORS — tighten origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else ["https://your-frontend.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting — 100 req/min per authenticated user (configurable)
rate_limit_store = RateLimitStore()
app.add_middleware(
    RateLimitMiddleware,
    rate_limit_store=rate_limit_store,
    limit=settings.rate_limit_per_minute,
)

# Routers
app.include_router(auth_router)
app.include_router(tasks_router)
app.include_router(evaluations_router)
app.include_router(webhooks_router)

# Static files from the React build
_FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
_ASSETS_DIR = os.path.join(_FRONTEND_DIST, "assets")
if os.path.exists(_ASSETS_DIR):
    # Mount /assets to match Vite's default output (base="/")
    app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")


@app.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env, "version": "0.1.1"}


@app.get("/health/models", tags=["system"])
async def health_models() -> dict:
    """Dry-run health check for all configured LLM models."""
    from app.agents.litellm_router import get_router
    router = get_router()
    results = await router.health_check()
    all_ok = all(v["status"] == "ok" for v in results.values())
    return {"all_ok": all_ok, "models": results}


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str) -> FileResponse:
    """SPA fallback — serve index.html for any non-API route."""
    if full_path.startswith(("api/", "auth/", "docs", "redoc", "openapi")):
        raise HTTPException(status_code=404, detail="Not found")
    index = os.path.join(_FRONTEND_DIST, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Frontend not built")

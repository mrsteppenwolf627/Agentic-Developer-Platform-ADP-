"""In-memory rate limiting middleware for ADP (FASE 4.2).

Limits authenticated users to N requests/minute (configurable via RATE_LIMIT_PER_MINUTE).
Unauthenticated requests and excluded paths bypass the limiter entirely.

Excluded paths: /health, /health/models, /docs, /redoc, /openapi.json, /webhooks/*
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


_EXCLUDED_PATHS = frozenset([
    "/health",
    "/health/models",
    "/docs",
    "/redoc",
    "/openapi.json",
])


def _is_excluded(path: str) -> bool:
    if path in _EXCLUDED_PATHS:
        return True
    if path.startswith("/webhooks/"):
        return True
    # swagger/openapi assets served under /docs or /openapi.json
    if path.startswith("/docs/") or path.startswith("/redoc/"):
        return True
    return False


def _user_id_from_header(auth_header: Optional[str], jwt_secret: str, jwt_algorithm: str) -> Optional[str]:
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=[jwt_algorithm])
        return payload.get("sub")
    except Exception:
        return None


@dataclass
class RateLimitEntry:
    count: int = 0
    reset_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=1)
    )


class RateLimitStore:
    def __init__(self) -> None:
        self.data: Dict[str, RateLimitEntry] = {}

    def clear(self) -> None:
        self.data.clear()

    def get_or_create(self, user_id: str) -> RateLimitEntry:
        if user_id not in self.data:
            self.data[user_id] = RateLimitEntry()
        return self.data[user_id]

    def is_expired(self, entry: RateLimitEntry) -> bool:
        return datetime.now(timezone.utc) >= entry.reset_at

    def reset(self, entry: RateLimitEntry) -> None:
        entry.count = 0
        entry.reset_at = datetime.now(timezone.utc) + timedelta(minutes=1)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        rate_limit_store: Optional[RateLimitStore] = None,
        limit: int = 100,
    ) -> None:
        super().__init__(app)
        self.store = rate_limit_store or RateLimitStore()
        self.limit = limit

    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_excluded(request.url.path):
            return await call_next(request)

        # Lazy import so tests can monkeypatch env before settings are cached
        from app.config import get_settings
        settings = get_settings()

        user_id = _user_id_from_header(
            request.headers.get("Authorization"),
            settings.jwt_secret,
            settings.jwt_algorithm,
        )

        if not user_id:
            return await call_next(request)

        entry = self.store.get_or_create(user_id)

        if self.store.is_expired(entry):
            self.store.reset(entry)

        if entry.count >= self.limit:
            retry_after = max(0, int((entry.reset_at - datetime.now(timezone.utc)).total_seconds()))
            reset_ts = int(entry.reset_at.timestamp())
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Retry after 60 seconds"},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_ts),
                },
            )

        entry.count += 1
        remaining = self.limit - entry.count

        response = await call_next(request)

        reset_ts = int(entry.reset_at.timestamp())
        response.headers["X-RateLimit-Limit"] = str(self.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_ts)

        return response

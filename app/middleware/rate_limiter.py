"""In-memory sliding-window rate limiting middleware for ADP (FASE 4.2).

Limits authenticated users to N requests/minute (configurable via RATE_LIMIT_PER_MINUTE).
Unauthenticated requests and excluded paths bypass the limiter entirely.

Excluded paths: /health, /health/models, /docs, /redoc, /openapi.json, /webhooks/*
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Deque, Dict, Optional

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


_WINDOW_SECONDS = 60


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
    except (TypeError, ValueError, jwt.PyJWTError):
        return None


@dataclass
class RateLimitEntry:
    count: int = 0
    reset_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(seconds=_WINDOW_SECONDS)
    )
    timestamps: Deque[datetime] = field(default_factory=deque)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_at: datetime
    retry_after: int


class RateLimitStore:
    def __init__(self, window_seconds: int = _WINDOW_SECONDS) -> None:
        self.data: Dict[str, RateLimitEntry] = {}
        self.window_seconds = window_seconds
        self._lock = Lock()

    def clear(self) -> None:
        with self._lock:
            self.data.clear()

    def get_or_create(self, user_id: str) -> RateLimitEntry:
        with self._lock:
            if user_id not in self.data:
                self.data[user_id] = RateLimitEntry()
            return self.data[user_id]

    def is_expired(self, entry: RateLimitEntry) -> bool:
        return datetime.now(timezone.utc) >= entry.reset_at

    def reset(self, entry: RateLimitEntry) -> None:
        entry.count = 0
        entry.timestamps.clear()
        entry.reset_at = datetime.now(timezone.utc) + timedelta(seconds=self.window_seconds)

    def _prune(self, entry: RateLimitEntry, now: datetime) -> None:
        window_start = now - timedelta(seconds=self.window_seconds)
        while entry.timestamps and entry.timestamps[0] <= window_start:
            entry.timestamps.popleft()

        entry.count = len(entry.timestamps)
        if entry.timestamps:
            entry.reset_at = entry.timestamps[0] + timedelta(seconds=self.window_seconds)
        else:
            entry.reset_at = now + timedelta(seconds=self.window_seconds)

    def consume(
        self,
        user_id: str,
        limit: int,
        now: Optional[datetime] = None,
    ) -> RateLimitDecision:
        current_time = now or datetime.now(timezone.utc)

        with self._lock:
            entry = self.data.get(user_id)
            if entry is None:
                entry = RateLimitEntry(
                    reset_at=current_time + timedelta(seconds=self.window_seconds)
                )
                self.data[user_id] = entry

            self._prune(entry, current_time)

            if entry.count >= limit:
                retry_after = max(
                    0,
                    math.ceil((entry.reset_at - current_time).total_seconds()),
                )
                return RateLimitDecision(
                    allowed=False,
                    limit=limit,
                    remaining=0,
                    reset_at=entry.reset_at,
                    retry_after=retry_after,
                )

            entry.timestamps.append(current_time)
            entry.count = len(entry.timestamps)
            entry.reset_at = entry.timestamps[0] + timedelta(seconds=self.window_seconds)
            remaining = max(0, limit - entry.count)
            retry_after = max(
                0,
                math.ceil((entry.reset_at - current_time).total_seconds()),
            )
            return RateLimitDecision(
                allowed=True,
                limit=limit,
                remaining=remaining,
                reset_at=entry.reset_at,
                retry_after=retry_after,
            )


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
        if _is_excluded(request.url.path) or self.limit <= 0:
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

        decision = self.store.consume(user_id, limit=self.limit)
        reset_ts = int(decision.reset_at.timestamp())

        if not decision.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Retry after {decision.retry_after} seconds"
                },
                headers={
                    "Retry-After": str(decision.retry_after),
                    "X-RateLimit-Limit": str(decision.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_ts),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_ts)

        return response

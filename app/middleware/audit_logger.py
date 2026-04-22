"""Audit logging middleware for ADP (FASE 4.3).

Logs every authenticated request to the user_actions table as a fire-and-forget
background task. Failures are silently swallowed — audit errors must never
impact the main request lifecycle.

Excluded paths: /health, /health/models, /docs, /redoc, /openapi.json, /webhooks/*
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import Any, Dict, Optional, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_SENSITIVE_KEYS: Set[str] = {
    "password",
    "token",
    "api_key",
    "secret",
    "access_token",
    "refresh_token",
    "password_hash",
}

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

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
    if path.startswith(("/webhooks/", "/docs/", "/redoc/")):
        return True
    return False


def _derive_action(method: str, path: str) -> str:
    parts = [p for p in path.strip("/").split("/") if p and not _UUID_RE.match(p)]
    return f"{method.upper()}:{'/'.join(parts) or '/'}"


def sanitize_body(data: Any) -> Any:
    """Recursively replace values of sensitive keys with '***'."""
    if isinstance(data, dict):
        return {
            k: "***" if k.lower() in _SENSITIVE_KEYS else sanitize_body(v)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [sanitize_body(item) for item in data]
    return data


async def write_audit_log(
    *,
    user_id: str,
    action: str,
    method: str,
    endpoint: str,
    status_code: int,
    ip_address: Optional[str],
    user_agent: Optional[str],
    request_body: Optional[Dict[str, Any]],
    duration_ms: int,
    error_message: Optional[str] = None,
) -> None:
    """Persist one audit entry using a fresh DB session. Failures are silent."""
    try:
        from app.database import AsyncSessionLocal
        from app.models.schemas import UserAction

        async with AsyncSessionLocal() as session:
            entry = UserAction(
                id=uuid.uuid4(),
                user_id=uuid.UUID(user_id),
                action=action,
                method=method,
                endpoint=endpoint,
                status_code=status_code,
                ip_address=ip_address,
                user_agent=user_agent,
                request_body=request_body,
                duration_ms=duration_ms,
                error_message=error_message,
            )
            session.add(entry)
            await session.commit()
    except Exception:
        pass


class AuditLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_excluded(request.url.path):
            return await call_next(request)

        from app.dependencies.security import get_user_id_from_token
        user_id = get_user_id_from_token(request.headers.get("Authorization"))

        if not user_id:
            return await call_next(request)

        raw_body = await request.body()
        request_body: Optional[Dict[str, Any]] = None
        if raw_body:
            try:
                parsed = json.loads(raw_body)
                request_body = sanitize_body(parsed)
            except (json.JSONDecodeError, ValueError):
                pass

        start = time.monotonic()
        response: Optional[Response] = None
        error_message: Optional[str] = None
        try:
            response = await call_next(request)
        except Exception as exc:
            error_message = str(exc)
            raise
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            status_code = response.status_code if response is not None else 500
            asyncio.ensure_future(
                write_audit_log(
                    user_id=user_id,
                    action=_derive_action(request.method, request.url.path),
                    method=request.method,
                    endpoint=request.url.path,
                    status_code=status_code,
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    request_body=request_body,
                    duration_ms=duration_ms,
                    error_message=error_message,
                )
            )

        return response

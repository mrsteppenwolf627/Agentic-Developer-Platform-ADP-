"""Audit logging tests for FASE 4.3."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.dependencies.security import create_access_token, hash_password
from app.middleware.audit_logger import AuditLoggerMiddleware, _derive_action, sanitize_body
from app.models.schemas import User, UserAction, UserRole
from tests.conftest import ScalarResult


def _make_user(role: UserRole = UserRole.user, email: str | None = None) -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        email=email or f"{role.value}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("password123"),
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}


def _make_request(
    *,
    path: str,
    method: str = "GET",
    body: object | None = None,
    headers: dict[str, str] | None = None,
) -> Request:
    raw_body = b""
    if body is not None:
        raw_body = json.dumps(body).encode("utf-8")

    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": raw_body, "more_body": False}

    raw_headers = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode("utf-8"), value.encode("utf-8")))

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "root_path": "",
        "query_string": b"",
        "headers": raw_headers,
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    return Request(scope, receive)


# ---------------------------------------------------------------------------
# Pure function tests - sanitize_body
# ---------------------------------------------------------------------------


def test_sanitize_body_masks_password():
    assert sanitize_body({"password": "s3cr3t"}) == {"password": "***"}


def test_sanitize_body_masks_token_and_api_key():
    result = sanitize_body({"token": "xyz", "api_key": "key123", "data": "safe"})
    assert result == {"token": "***", "api_key": "***", "data": "safe"}


def test_sanitize_body_masks_nested_password():
    result = sanitize_body({"user": {"password": "abc", "name": "alice"}})
    assert result == {"user": {"password": "***", "name": "alice"}}


def test_sanitize_body_masks_keys_case_insensitively():
    result = sanitize_body({"Password": "abc", "API_KEY": "key"})
    assert result == {"Password": "***", "API_KEY": "***"}


def test_sanitize_body_leaves_non_sensitive_unchanged():
    data = {"email": "a@b.com", "role": "admin", "count": 3}
    assert sanitize_body(data) == data


# ---------------------------------------------------------------------------
# Pure function tests - _derive_action
# ---------------------------------------------------------------------------


def test_derive_action_get_task_is_descriptive():
    uid = uuid.uuid4()
    assert _derive_action("GET", f"/api/tasks/{uid}") == "view_tasks"


def test_derive_action_register_is_descriptive():
    assert _derive_action("POST", "/auth/register") == "register"


def test_derive_action_execute_task_is_descriptive():
    uid = uuid.uuid4()
    assert _derive_action("POST", f"/api/tasks/{uid}/execute") == "execute_task"


def test_derive_action_view_all_is_descriptive():
    assert _derive_action("GET", "/audit/all") == "view_all_audit"


def test_derive_action_admin_create_user_is_descriptive():
    assert _derive_action("POST", "/auth/admin/users") == "create_admin_user"


def test_user_action_model_has_expected_columns_indexes_and_no_fk():
    table = UserAction.__table__

    assert "response_body" in table.c
    assert "metadata" in table.c
    assert len(table.c.user_id.foreign_keys) == 0

    index_names = {index.name for index in table.indexes}
    assert "ix_user_actions_created_at" in index_names
    assert "ix_user_actions_user_id" in index_names
    assert "ix_user_actions_method" in index_names
    assert "ix_user_actions_status_code" in index_names


# ---------------------------------------------------------------------------
# Middleware integration tests
# ---------------------------------------------------------------------------


def test_authenticated_request_triggers_audit_and_captures_response_body(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)

    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock) as mock_write:
        response = client.get("/auth/me", headers=_headers(user))

    assert response.status_code == 200
    mock_write.assert_called_once()
    kw = mock_write.call_args.kwargs
    assert kw["user_id"] == str(user.id)
    assert kw["method"] == "GET"
    assert kw["endpoint"] == "/auth/me"
    assert kw["status_code"] == 200
    assert kw["response_body"] is not None
    assert len(kw["response_body"]) <= 500


def test_unauthenticated_request_not_audited(client):
    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock) as mock_write:
        client.get("/auth/me")

    mock_write.assert_not_called()


def test_health_endpoint_not_audited(client):
    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock) as mock_write:
        client.get("/health")

    mock_write.assert_not_called()


def test_audit_captures_descriptive_action_name(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)

    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock) as mock_write:
        client.get("/auth/me", headers=_headers(user))

    assert mock_write.call_args.kwargs["action"] == "view_auth_me"


def test_audit_captures_duration_ms(client, mock_db):
    user = _make_user()
    mock_db.execute.return_value = ScalarResult(user)

    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock) as mock_write:
        client.get("/auth/me", headers=_headers(user))

    kw = mock_write.call_args.kwargs
    assert isinstance(kw["duration_ms"], int)
    assert kw["duration_ms"] >= 0


def test_audit_captures_status_code_for_error(client, mock_db):
    user = _make_user(role=UserRole.user)
    mock_db.execute.return_value = ScalarResult(user)

    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock) as mock_write:
        response = client.post(f"/api/tasks/{uuid.uuid4()}/execute", headers=_headers(user))

    assert response.status_code == 403
    assert mock_write.call_args.kwargs["status_code"] == 403


@pytest.mark.asyncio
async def test_audit_logs_with_very_large_request_body():
    user = _make_user(role=UserRole.developer)
    middleware = AuditLoggerMiddleware(app=lambda scope, receive, send: None)
    request = _make_request(
        path="/api/evaluations/123",
        method="POST",
        body={"password": "secret", "payload": "x" * 6000},
        headers=_headers(user),
    )

    async def call_next(_: Request) -> JSONResponse:
        return JSONResponse({"token": "jwt.secret", "payload": "y" * 800}, status_code=201)

    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock) as mock_write:
        response = await middleware.dispatch(request, call_next)
        await asyncio.sleep(0)

    assert response.status_code == 201
    kw = mock_write.call_args.kwargs
    assert kw["request_body"]["password"] == "***"
    assert len(kw["request_body"]["payload"]) == 6000
    assert kw["response_body"] is not None
    assert len(kw["response_body"]) == 500
    assert "***" in kw["response_body"]


@pytest.mark.asyncio
async def test_audit_logs_concurrent_requests():
    user = _make_user()
    middleware = AuditLoggerMiddleware(app=lambda scope, receive, send: None)

    async def call_next(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True}, status_code=200)

    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock) as mock_write:
        await asyncio.gather(
            *[
                middleware.dispatch(
                    _make_request(path="/auth/me", headers=_headers(user)),
                    call_next,
                )
                for _ in range(5)
            ]
        )
        await asyncio.sleep(0)

    assert mock_write.call_count == 5


# ---------------------------------------------------------------------------
# GET /audit endpoint tests
# ---------------------------------------------------------------------------


def test_get_my_audit_requires_auth(client):
    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock):
        response = client.get("/audit")
    assert response.status_code == 401


def test_get_my_audit_returns_list(client, mock_db):
    user = _make_user()
    mock_db.execute.side_effect = [
        ScalarResult(user),
        ScalarResult([]),
    ]

    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock):
        response = client.get("/audit", headers=_headers(user))

    assert response.status_code == 200
    assert response.json() == []


def test_audit_pagination_uses_skip_limit(client, mock_db):
    user = _make_user()
    mock_db.execute.side_effect = [
        ScalarResult(user),
        ScalarResult([]),
    ]

    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock):
        response = client.get("/audit?skip=10&limit=5", headers=_headers(user))

    assert response.status_code == 200
    stmt = mock_db.execute.await_args_list[1].args[0]
    assert stmt._limit_clause.value == 5
    assert stmt._offset_clause.value == 10


def test_admin_can_access_all_audit(client, mock_db):
    admin = _make_user(role=UserRole.admin)
    mock_db.execute.side_effect = [
        ScalarResult(admin),
        ScalarResult([]),
    ]

    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock):
        response = client.get("/audit/all", headers=_headers(admin))

    assert response.status_code == 200
    assert response.json() == []


def test_non_admin_denied_all_audit(client, mock_db):
    developer = _make_user(role=UserRole.developer)
    mock_db.execute.return_value = ScalarResult(developer)

    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock):
        response = client.get("/audit/all", headers=_headers(developer))

    assert response.status_code == 403


def test_admin_can_filter_by_user_id(client, mock_db):
    admin = _make_user(role=UserRole.admin)
    target_id = uuid.uuid4()
    mock_db.execute.side_effect = [
        ScalarResult(admin),
        ScalarResult([]),
    ]

    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock):
        response = client.get(f"/audit/all?user_id={target_id}", headers=_headers(admin))

    assert response.status_code == 200
    stmt = mock_db.execute.await_args_list[1].args[0]
    compiled = stmt.compile()
    assert target_id in compiled.params.values()


def test_audit_all_pagination_uses_skip_limit(client, mock_db):
    admin = _make_user(role=UserRole.admin)
    mock_db.execute.side_effect = [
        ScalarResult(admin),
        ScalarResult([]),
    ]

    with patch("app.middleware.audit_logger.write_audit_log", new_callable=AsyncMock):
        response = client.get("/audit/all?skip=20&limit=7", headers=_headers(admin))

    assert response.status_code == 200
    stmt = mock_db.execute.await_args_list[1].args[0]
    assert stmt._limit_clause.value == 7
    assert stmt._offset_clause.value == 20

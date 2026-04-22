"""RBAC tests — verifies role-based access control on all protected endpoints.

Coverage:
  - 401 for unauthenticated requests (no token)
  - 403 for authenticated users with insufficient role
  - 200/201 for users with the required role

Role matrix:
  execute / rollback     → admin, developer (not user)
  read tasks             → admin, developer, user
  evaluate / get eval    → admin, developer (not user)
  admin create user      → admin only
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import get_settings
from app.dependencies.security import create_access_token, hash_password
from app.models.schemas import (
    AgentModel,
    Task,
    TaskStatus,
    Ticket,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
)
from tests.conftest import ScalarResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-with-32-plus-bytes")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("JWT_EXPIRATION_MINUTES", "15")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_user(role: UserRole, email: str | None = None) -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        email=email or f"{role.value}@example.com",
        password_hash=hash_password("password123"),
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}


def _make_task(ticket_id: uuid.UUID | None = None) -> Task:
    now = datetime.now(timezone.utc)
    task = Task(
        id=uuid.uuid4(),
        ticket_id=ticket_id or uuid.uuid4(),
        name="Test task",
        assigned_model=AgentModel.claude,
        status=TaskStatus.pending,
        dependencies=[],
        prompt_sent=None,
        output=None,
        execution_log=None,
        created_at=now,
        updated_at=now,
    )
    task.ticket = Ticket(
        id=task.ticket_id,
        title="Test ticket",
        status=TicketStatus.pending,
        priority=TicketPriority.P2,
        created_at=now,
        updated_at=now,
    )
    task.evaluations = []
    task.agent_sessions = []
    task.rollback_entries = []
    return task


# ---------------------------------------------------------------------------
# GET /api/tasks/{task_id} — all roles allowed
# ---------------------------------------------------------------------------

def test_get_task_admin_allowed(client, mock_db):
    admin = _make_user(UserRole.admin)
    task = _make_task()
    mock_db.execute.side_effect = [ScalarResult(admin), ScalarResult(task)]

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=task)):
        response = client.get(f"/api/tasks/{task.id}", headers=_headers(admin))

    assert response.status_code == 200


def test_get_task_developer_allowed(client, mock_db):
    dev = _make_user(UserRole.developer)
    task = _make_task()
    mock_db.execute.side_effect = [ScalarResult(dev)]

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=task)):
        response = client.get(f"/api/tasks/{task.id}", headers=_headers(dev))

    assert response.status_code == 200


def test_get_task_user_allowed(client, mock_db):
    user = _make_user(UserRole.user)
    task = _make_task()
    mock_db.execute.side_effect = [ScalarResult(user)]

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=task)):
        response = client.get(f"/api/tasks/{task.id}", headers=_headers(user))

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/tasks/{task_id}/execute — admin and developer only
# ---------------------------------------------------------------------------

def test_execute_task_user_forbidden(client, mock_db):
    user = _make_user(UserRole.user)
    mock_db.execute.return_value = ScalarResult(user)

    response = client.post(
        f"/api/tasks/{uuid.uuid4()}/execute",
        headers=_headers(user),
    )

    assert response.status_code == 403
    assert "admin" in response.json()["detail"] or "developer" in response.json()["detail"]


def test_execute_task_no_token_returns_401(client):
    response = client.post(f"/api/tasks/{uuid.uuid4()}/execute")
    assert response.status_code == 401


def test_execute_task_admin_passes_auth(client, mock_db):
    admin = _make_user(UserRole.admin)
    task = _make_task()
    mock_db.execute.side_effect = [ScalarResult(admin), ScalarResult(task)]

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=task)), \
         patch("app.services.task_executor.TaskExecutor.execute_task", new=AsyncMock()) as mock_exec:
        from app.services.task_executor import TaskResult
        mock_exec.return_value = TaskResult(
            task_id=task.id, success=True, output="ok",
            model_used="claude-sonnet-4-6", tokens_total=100, latency_ms=200, attempt=1,
        )
        response = client.post(f"/api/tasks/{task.id}/execute", headers=_headers(admin))

    assert response.status_code != 403
    assert response.status_code != 401


def test_execute_task_developer_passes_auth(client, mock_db):
    dev = _make_user(UserRole.developer)
    task = _make_task()
    mock_db.execute.side_effect = [ScalarResult(dev), ScalarResult(task)]

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=task)), \
         patch("app.services.task_executor.TaskExecutor.execute_task", new=AsyncMock()) as mock_exec:
        from app.services.task_executor import TaskResult
        mock_exec.return_value = TaskResult(
            task_id=task.id, success=True, output="ok",
            model_used="claude-sonnet-4-6", tokens_total=100, latency_ms=200, attempt=1,
        )
        response = client.post(f"/api/tasks/{task.id}/execute", headers=_headers(dev))

    assert response.status_code != 403
    assert response.status_code != 401


# ---------------------------------------------------------------------------
# POST /api/tasks/{task_id}/rollback — admin and developer only
# ---------------------------------------------------------------------------

def test_rollback_user_forbidden(client, mock_db):
    user = _make_user(UserRole.user)
    mock_db.execute.return_value = ScalarResult(user)

    response = client.post(
        f"/api/tasks/{uuid.uuid4()}/rollback",
        json={"rollback_id": None},
        headers=_headers(user),
    )

    assert response.status_code == 403


def test_rollback_no_token_returns_401(client):
    response = client.post(
        f"/api/tasks/{uuid.uuid4()}/rollback",
        json={"rollback_id": None},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/evaluations/{task_id} — admin and developer only
# ---------------------------------------------------------------------------

def test_evaluate_task_user_forbidden(client, mock_db):
    user = _make_user(UserRole.user)
    mock_db.execute.return_value = ScalarResult(user)

    response = client.post(
        f"/api/evaluations/{uuid.uuid4()}",
        json={"output_code": "print('hello')"},
        headers=_headers(user),
    )

    assert response.status_code == 403


def test_evaluate_task_no_token_returns_401(client):
    response = client.post(
        f"/api/evaluations/{uuid.uuid4()}",
        json={"output_code": "print('hello')"},
    )
    assert response.status_code == 401


def test_evaluate_task_developer_passes_auth(client, mock_db):
    from app.services.evaluation_engine import EvaluationResult
    dev = _make_user(UserRole.developer)
    task = _make_task()
    mock_db.execute.side_effect = [ScalarResult(dev), ScalarResult(task)]

    eval_result = EvaluationResult(
        task_id=task.id, passed=True, score=1.0, findings=[], pillars=[]
    )

    with patch("app.api.evaluations._get_task_or_404", new=AsyncMock(return_value=task)), \
         patch("app.services.task_executor.TaskExecutor.evaluate_task_output",
               new=AsyncMock(return_value=eval_result)):
        response = client.post(
            f"/api/evaluations/{task.id}",
            json={"output_code": "print('hello')"},
            headers=_headers(dev),
        )

    assert response.status_code != 403
    assert response.status_code != 401


# ---------------------------------------------------------------------------
# GET /api/evaluations/{task_id} — admin and developer only
# ---------------------------------------------------------------------------

def test_get_evaluation_user_forbidden(client, mock_db):
    user = _make_user(UserRole.user)
    mock_db.execute.return_value = ScalarResult(user)

    response = client.get(
        f"/api/evaluations/{uuid.uuid4()}",
        headers=_headers(user),
    )

    assert response.status_code == 403


def test_get_evaluation_no_token_returns_401(client):
    response = client.get(f"/api/evaluations/{uuid.uuid4()}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /auth/admin/users — admin only
# ---------------------------------------------------------------------------

def test_admin_create_user_success(client, mock_db):
    admin = _make_user(UserRole.admin)
    mock_db.execute.side_effect = [ScalarResult(admin), ScalarResult(None)]

    async def assign_defaults(obj):
        now = datetime.now(timezone.utc)
        obj.id = uuid.uuid4()
        obj.is_active = True
        obj.created_at = now
        obj.updated_at = now

    mock_db.refresh.side_effect = assign_defaults

    response = client.post(
        "/auth/admin/users",
        json={"email": "newdev@example.com", "password": "password123", "role": "developer"},
        headers=_headers(admin),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "newdev@example.com"
    assert payload["role"] == "developer"
    assert "password_hash" not in payload


def test_admin_create_user_developer_forbidden(client, mock_db):
    dev = _make_user(UserRole.developer)
    mock_db.execute.return_value = ScalarResult(dev)

    response = client.post(
        "/auth/admin/users",
        json={"email": "test@example.com", "password": "password123", "role": "user"},
        headers=_headers(dev),
    )

    assert response.status_code == 403


def test_admin_create_user_user_role_forbidden(client, mock_db):
    user = _make_user(UserRole.user)
    mock_db.execute.return_value = ScalarResult(user)

    response = client.post(
        "/auth/admin/users",
        json={"email": "test@example.com", "password": "password123"},
        headers=_headers(user),
    )

    assert response.status_code == 403


def test_admin_create_user_no_token_returns_401(client):
    response = client.post(
        "/auth/admin/users",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 401


def test_admin_create_user_duplicate_email(client, mock_db):
    admin = _make_user(UserRole.admin)
    existing = _make_user(UserRole.user, email="existing@example.com")
    mock_db.execute.side_effect = [ScalarResult(admin), ScalarResult(existing)]

    response = client.post(
        "/auth/admin/users",
        json={"email": "existing@example.com", "password": "password123"},
        headers=_headers(admin),
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# 403 response format check
# ---------------------------------------------------------------------------

def test_forbidden_response_has_detail(client, mock_db):
    user = _make_user(UserRole.user)
    mock_db.execute.return_value = ScalarResult(user)

    response = client.post(
        f"/api/tasks/{uuid.uuid4()}/execute",
        headers=_headers(user),
    )

    assert response.status_code == 403
    body = response.json()
    assert "detail" in body
    assert "admin" in body["detail"] or "developer" in body["detail"]

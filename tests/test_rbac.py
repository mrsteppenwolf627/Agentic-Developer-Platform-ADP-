"""RBAC tests for role-based authorization on protected endpoints.

The suite keeps the original 20-test target while covering:
  - 401 for missing/invalid tokens
  - 403 with a clear role-based message
  - User/developer/admin authorization matrix
  - Admin-only user creation with explicit role assignment
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.config import get_settings
from app.dependencies.security import create_access_token, hash_password, require_role
from app.models.schemas import (
    AgentModel,
    Evaluation,
    EvaluationModel,
    EvaluationType,
    Task,
    TaskStatus,
    Ticket,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
)
from tests.conftest import ScalarResult


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


def _invalid_headers() -> dict[str, str]:
    return {"Authorization": "Bearer invalid-token"}


def _make_task(ticket_id: uuid.UUID | None = None, output: str | None = "print('ok')") -> Task:
    now = datetime.now(timezone.utc)
    task = Task(
        id=uuid.uuid4(),
        ticket_id=ticket_id or uuid.uuid4(),
        name="Test task",
        assigned_model=AgentModel.claude,
        status=TaskStatus.pending,
        dependencies=[],
        prompt_sent=None,
        output=output,
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


def _make_evaluation(task_id: uuid.UUID) -> Evaluation:
    return Evaluation(
        id=uuid.uuid4(),
        task_id=task_id,
        evaluation_type=EvaluationType.security,
        score=0.95,
        findings={"issues": [], "pillar": "SECURITY"},
        passed=True,
        evaluated_by=EvaluationModel.codex,
        created_at=datetime.now(timezone.utc),
    )


async def _assign_refreshed_user(obj: User) -> None:
    now = datetime.now(timezone.utc)
    obj.id = uuid.uuid4()
    obj.is_active = True
    obj.created_at = now
    obj.updated_at = now
    if getattr(obj, "role", None) is None:
        obj.role = UserRole.user


def test_valid_token_returns_200(client, mock_db):
    admin = _make_user(UserRole.admin)
    developer = _make_user(UserRole.developer)
    user = _make_user(UserRole.user)
    task = _make_task()

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=task)), patch(
        "app.api.tasks._get_ticket_or_404",
        new=AsyncMock(return_value=task.ticket),
    ):
        mock_db.execute.side_effect = [ScalarResult(admin)]
        admin_response = client.get(f"/api/tasks/{task.id}", headers=_headers(admin))

        mock_db.execute.side_effect = [ScalarResult(developer)]
        developer_response = client.get(f"/api/tasks/{task.id}", headers=_headers(developer))

        mock_db.execute.side_effect = [ScalarResult(user), ScalarResult([task])]
        user_response = client.get(f"/api/tasks/ticket/{task.ticket_id}", headers=_headers(user))

    assert admin_response.status_code == 200
    assert developer_response.status_code == 200
    assert user_response.status_code == 200


def test_admin_can_execute_task(client, mock_db):
    from app.services.task_executor import TaskResult

    admin = _make_user(UserRole.admin)
    task = _make_task(output=None)
    mock_db.execute.side_effect = [ScalarResult(admin)]

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=task)), patch(
        "app.api.tasks.TaskExecutor.execute_task",
        new=AsyncMock(
            return_value=TaskResult(
                task_id=task.id,
                success=True,
                output="ok",
                model_used="claude-sonnet-4-6",
                tokens_total=100,
                latency_ms=200,
                attempt=1,
            )
        ),
    ):
        response = client.post(f"/api/tasks/{task.id}/execute", headers=_headers(admin))

    assert response.status_code == 200


def test_developer_can_execute_task(client, mock_db):
    from app.services.task_executor import TaskResult

    developer = _make_user(UserRole.developer)
    task = _make_task(output=None)
    mock_db.execute.side_effect = [ScalarResult(developer)]

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=task)), patch(
        "app.api.tasks.TaskExecutor.execute_task",
        new=AsyncMock(
            return_value=TaskResult(
                task_id=task.id,
                success=True,
                output="ok",
                model_used="claude-sonnet-4-6",
                tokens_total=100,
                latency_ms=200,
                attempt=1,
            )
        ),
    ):
        response = client.post(f"/api/tasks/{task.id}/execute", headers=_headers(developer))

    assert response.status_code == 200


def test_user_cannot_execute_task(client, mock_db):
    user = _make_user(UserRole.user)
    mock_db.execute.return_value = ScalarResult(user)

    response = client.post(f"/api/tasks/{uuid.uuid4()}/execute", headers=_headers(user))

    assert response.status_code == 403


def test_admin_can_rollback_task(client, mock_db):
    admin = _make_user(UserRole.admin)
    task = _make_task()
    rollback_id = uuid.uuid4()
    mock_db.execute.side_effect = [ScalarResult(admin)]

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=task)), patch(
        "app.api.tasks.ContextManager.get_latest_rollback",
        new=AsyncMock(return_value=type("Rollback", (), {"id": rollback_id})()),
    ), patch(
        "app.api.tasks.ContextManager.restore_context",
        new=AsyncMock(return_value=True),
    ):
        response = client.post(
            f"/api/tasks/{task.id}/rollback",
            json={"rollback_id": None},
            headers=_headers(admin),
        )

    assert response.status_code == 200


def test_developer_can_rollback_task(client, mock_db):
    developer = _make_user(UserRole.developer)
    task = _make_task()
    rollback_id = uuid.uuid4()
    mock_db.execute.side_effect = [ScalarResult(developer)]

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=task)), patch(
        "app.api.tasks.ContextManager.get_latest_rollback",
        new=AsyncMock(return_value=type("Rollback", (), {"id": rollback_id})()),
    ), patch(
        "app.api.tasks.ContextManager.restore_context",
        new=AsyncMock(return_value=True),
    ):
        response = client.post(
            f"/api/tasks/{task.id}/rollback",
            json={"rollback_id": None},
            headers=_headers(developer),
        )

    assert response.status_code == 200


def test_user_cannot_rollback_task(client, mock_db):
    user = _make_user(UserRole.user)
    mock_db.execute.return_value = ScalarResult(user)

    response = client.post(
        f"/api/tasks/{uuid.uuid4()}/rollback",
        json={"rollback_id": None},
        headers=_headers(user),
    )

    assert response.status_code == 403


def test_admin_can_create_evaluation(client, mock_db):
    from app.services.evaluation_engine import EvaluationResult

    admin = _make_user(UserRole.admin)
    task = _make_task()
    mock_db.execute.side_effect = [ScalarResult(admin)]

    with patch("app.api.evaluations._get_task_or_404", new=AsyncMock(return_value=task)), patch(
        "app.api.evaluations.TaskExecutor.evaluate_task_output",
        new=AsyncMock(
            return_value=EvaluationResult(
                task_id=task.id,
                passed=True,
                score=1.0,
                findings=[],
                pillars=[],
            )
        ),
    ):
        response = client.post(
            f"/api/evaluations/{task.id}",
            json={"output_code": "print('ok')"},
            headers=_headers(admin),
        )

    assert response.status_code == 200


def test_developer_can_create_evaluation(client, mock_db):
    from app.services.evaluation_engine import EvaluationResult

    developer = _make_user(UserRole.developer)
    task = _make_task()
    mock_db.execute.side_effect = [ScalarResult(developer)]

    with patch("app.api.evaluations._get_task_or_404", new=AsyncMock(return_value=task)), patch(
        "app.api.evaluations.TaskExecutor.evaluate_task_output",
        new=AsyncMock(
            return_value=EvaluationResult(
                task_id=task.id,
                passed=True,
                score=1.0,
                findings=[],
                pillars=[],
            )
        ),
    ):
        response = client.post(
            f"/api/evaluations/{task.id}",
            json={"output_code": "print('ok')"},
            headers=_headers(developer),
        )

    assert response.status_code == 200


def test_user_cannot_create_evaluation(client, mock_db):
    user = _make_user(UserRole.user)
    mock_db.execute.return_value = ScalarResult(user)

    response = client.post(
        f"/api/evaluations/{uuid.uuid4()}",
        json={"output_code": "print('ok')"},
        headers=_headers(user),
    )

    assert response.status_code == 403


def test_user_can_view_evaluation(client, mock_db):
    user = _make_user(UserRole.user)
    task = _make_task()
    evaluation = _make_evaluation(task.id)
    mock_db.execute.side_effect = [ScalarResult(user), ScalarResult([evaluation])]

    with patch("app.api.evaluations._get_task_or_404", new=AsyncMock(return_value=task)):
        response = client.get(f"/api/evaluations/{task.id}", headers=_headers(user))

    assert response.status_code == 200
    assert response.json()["task_id"] == str(task.id)


def test_admin_endpoint_requires_admin_role(client, mock_db):
    developer = _make_user(UserRole.developer)
    user = _make_user(UserRole.user)

    mock_db.execute.side_effect = [ScalarResult(developer)]
    developer_response = client.post(
        "/auth/admin/users",
        json={"email": "dev-blocked@example.com", "password": "password123", "role": "user"},
        headers=_headers(developer),
    )

    mock_db.execute.side_effect = [ScalarResult(user)]
    user_response = client.post(
        "/auth/admin/users",
        json={"email": "user-blocked@example.com", "password": "password123", "role": "user"},
        headers=_headers(user),
    )

    assert developer_response.status_code == 403
    assert user_response.status_code == 403


def test_admin_can_create_user_with_role(client, mock_db):
    admin = _make_user(UserRole.admin)
    mock_db.execute.side_effect = [ScalarResult(admin), ScalarResult(None)]
    mock_db.refresh.side_effect = _assign_refreshed_user

    response = client.post(
        "/auth/admin/users",
        json={"email": "newdev@example.com", "password": "password123", "role": "developer"},
        headers=_headers(admin),
    )

    assert response.status_code == 201
    assert response.json()["role"] == "developer"


def test_missing_token_returns_401(client):
    execute_response = client.post(f"/api/tasks/{uuid.uuid4()}/execute")
    admin_response = client.post(
        "/auth/admin/users",
        json={"email": "missing-token@example.com", "password": "password123", "role": "user"},
    )

    assert execute_response.status_code == 401
    assert admin_response.status_code == 401


def test_invalid_token_returns_401(client):
    me_response = client.get("/auth/me", headers=_invalid_headers())
    execute_response = client.post(
        f"/api/tasks/{uuid.uuid4()}/execute",
        headers=_invalid_headers(),
    )

    assert me_response.status_code == 401
    assert execute_response.status_code == 401


def test_403_response_has_correct_detail_message(client, mock_db):
    user = _make_user(UserRole.user)
    mock_db.execute.return_value = ScalarResult(user)

    response = client.post(f"/api/tasks/{uuid.uuid4()}/execute", headers=_headers(user))

    assert response.status_code == 403
    assert response.json()["detail"] == "Acceso denegado. Se requieren roles: admin, developer"


def test_get_me_returns_correct_role(client, mock_db):
    developer = _make_user(UserRole.developer)
    mock_db.execute.return_value = ScalarResult(developer)

    response = client.get("/auth/me", headers=_headers(developer))

    assert response.status_code == 200
    assert response.json()["role"] == "developer"


def test_multiple_roles_in_decorator():
    checker = require_role([UserRole.admin, UserRole.developer])
    developer = _make_user(UserRole.developer)
    user = _make_user(UserRole.user)

    allowed = asyncio.run(checker(current_user=developer))
    assert allowed.role == UserRole.developer

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(checker(current_user=user))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Acceso denegado. Se requieren roles: admin, developer"


def test_role_immutable_after_user_creation(client, mock_db):
    mock_db.execute.return_value = ScalarResult(None)
    mock_db.refresh.side_effect = _assign_refreshed_user

    response = client.post(
        "/auth/register",
        json={"email": "plain-user@example.com", "password": "password123", "role": "admin"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "user"


def test_duplicate_email_returns_409_for_admin_create_user(client, mock_db):
    admin = _make_user(UserRole.admin)
    existing = _make_user(UserRole.user, email="existing@example.com")
    mock_db.execute.side_effect = [ScalarResult(admin), ScalarResult(existing)]

    response = client.post(
        "/auth/admin/users",
        json={"email": "existing@example.com", "password": "password123", "role": "developer"},
        headers=_headers(admin),
    )

    assert response.status_code == 409

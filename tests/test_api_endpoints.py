from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.schemas import TaskStatus
from app.services.task_executor import TaskResult
from tests.conftest import ScalarResult


def test_post_execute_task_returns_200_and_payload(client, mock_db, sample_task, auth_user, auth_headers):
    task_result = TaskResult(
        task_id=sample_task.id,
        success=True,
        output="generated code",
        model_used="claude-sonnet-4-6",
        tokens_total=100,
        latency_ms=200,
        attempt=1,
        rollback_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=sample_task)), patch(
        "app.api.tasks.TaskExecutor.execute_task",
        new=AsyncMock(return_value=task_result),
    ):
        mock_db.execute.side_effect = [ScalarResult(auth_user)]
        response = client.post(f"/api/tasks/{sample_task.id}/execute", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["task_id"] == str(sample_task.id)


def test_get_task_returns_task_detail(client, mock_db, sample_task, sample_evaluation, auth_user, auth_headers):
    sample_task.evaluations = [sample_evaluation]
    sample_task.agent_sessions = []
    sample_task.rollback_entries = []

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=sample_task)):
        mock_db.execute.side_effect = [ScalarResult(auth_user)]
        response = client.get(f"/api/tasks/{sample_task.id}", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["id"] == str(sample_task.id)
    assert payload["evaluations"][0]["score"] == sample_evaluation.score


def test_get_tasks_by_ticket_returns_list(client, mock_db, sample_ticket, sample_task, auth_user, auth_headers):
    with patch("app.api.tasks._get_ticket_or_404", new=AsyncMock(return_value=sample_ticket)):
        mock_db.execute.side_effect = [ScalarResult(auth_user), ScalarResult([sample_task])]
        response = client.get(f"/api/tasks/ticket/{sample_ticket.id}", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == str(sample_task.id)


def test_post_rollback_restores_context(client, mock_db, sample_task, auth_user, auth_headers):
    sample_task.status = TaskStatus.failed
    rollback_id = uuid.uuid4()

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=sample_task)), patch(
        "app.api.tasks.ContextManager.get_latest_rollback",
        new=AsyncMock(return_value=SimpleNamespace(id=rollback_id)),
    ), patch(
        "app.api.tasks.ContextManager.restore_context",
        new=AsyncMock(return_value=True),
    ):
        mock_db.execute.side_effect = [ScalarResult(auth_user)]
        response = client.post(
            f"/api/tasks/{sample_task.id}/rollback",
            json={},
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["restored"] is True
    assert sample_task.status is TaskStatus.pending

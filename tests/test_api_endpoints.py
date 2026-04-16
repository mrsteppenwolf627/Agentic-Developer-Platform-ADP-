from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.schemas import TaskResponse, TaskStatus
from app.services.task_executor import TaskResult
from tests.conftest import ScalarResult


def test_post_execute_task_returns_200_and_payload(client, mock_db, sample_task):
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
        response = client.post(f"/api/tasks/{sample_task.id}/execute")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["task_id"] == str(sample_task.id)


def test_get_task_returns_task_detail(client, sample_task, sample_evaluation):
    sample_task.evaluations = [sample_evaluation]
    sample_task.agent_sessions = []
    sample_task.rollback_entries = []

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=sample_task)):
        response = client.get(f"/api/tasks/{sample_task.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["id"] == str(sample_task.id)
    assert payload["evaluations"][0]["score"] == sample_evaluation.score


def test_get_tasks_by_ticket_returns_list(client, mock_db, sample_ticket, sample_task):
    with patch("app.api.tasks._get_ticket_or_404", new=AsyncMock(return_value=sample_ticket)):
        mock_db.execute.return_value = ScalarResult([sample_task])
        response = client.get(f"/api/tasks/ticket/{sample_ticket.id}")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == str(sample_task.id)


def test_post_rollback_restores_context(client, sample_task):
    sample_task.status = TaskStatus.failed
    rollback_id = uuid.uuid4()

    with patch("app.api.tasks._get_task_or_404", new=AsyncMock(return_value=sample_task)), patch(
        "app.api.tasks.ContextManager.get_latest_rollback",
        new=AsyncMock(return_value=SimpleNamespace(id=rollback_id)),
    ), patch(
        "app.api.tasks.ContextManager.restore_context",
        new=AsyncMock(return_value=True),
    ):
        response = client.post(f"/api/tasks/{sample_task.id}/rollback", json={})

    assert response.status_code == 200
    assert response.json()["restored"] is True
    assert sample_task.status is TaskStatus.pending

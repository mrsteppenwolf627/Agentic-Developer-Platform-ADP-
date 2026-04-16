from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import TaskStatus
from app.services.context_manager import ContextState
from app.services.task_executor import TaskExecutor


@pytest.mark.asyncio
async def test_execute_task_happy_path(mock_db, mock_router, mock_context_manager, sample_task):
    executor = TaskExecutor(db=mock_db, router=mock_router, context_manager=mock_context_manager)

    with patch.object(executor, "_load_task", AsyncMock(return_value=sample_task)), patch(
        "app.services.task_executor._resolve_dependencies",
        new=AsyncMock(return_value=[]),
    ):
        result = await executor.execute_task(sample_task.id)

    assert result.success is True
    assert sample_task.status is TaskStatus.in_progress
    assert sample_task.output == "def generated() -> str:\n    return 'ok'\n"
    assert sample_task.prompt_sent is not None
    assert sample_task.execution_log["steps"][0]["model"] == "claude-sonnet-4-6"
    mock_context_manager.snapshot_context.assert_awaited_once()
    mock_context_manager.mark_rollback_applied.assert_awaited_once()
    mock_router.route_task.assert_awaited_once()
    assert mock_router.route_task.await_args.kwargs["db"] is mock_db


@pytest.mark.asyncio
async def test_execute_task_with_unresolved_dependencies_returns_dependency_error(
    mock_db,
    mock_router,
    mock_context_manager,
    sample_task,
):
    executor = TaskExecutor(db=mock_db, router=mock_router, context_manager=mock_context_manager)
    unresolved = [uuid.uuid4()]

    with patch.object(executor, "_load_task", AsyncMock(return_value=sample_task)), patch(
        "app.services.task_executor._resolve_dependencies",
        new=AsyncMock(return_value=unresolved),
    ):
        result = await executor.execute_task(sample_task.id)

    assert result.success is False
    assert result.error_type == "dependency_unmet"
    mock_router.route_task.assert_not_called()


@pytest.mark.asyncio
async def test_execute_task_rejects_double_execution(mock_db, mock_router, mock_context_manager, sample_task):
    executor = TaskExecutor(db=mock_db, router=mock_router, context_manager=mock_context_manager)
    sample_task.status = TaskStatus.completed

    with patch.object(executor, "_load_task", AsyncMock(return_value=sample_task)):
        result = await executor.execute_task(sample_task.id)

    assert result.success is False
    assert result.error_type == "invalid_state"
    mock_router.route_task.assert_not_called()


from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.smart_router import ComponentAnalysis, ExecutionMode, ExecutionPlan
from app.models.schemas import AgentModel, Task, TaskStatus, Ticket, TicketPriority, TicketStatus
from app.services.task_executor import TaskExecutor, TaskResult


def _ticket_with_tasks() -> tuple[Ticket, list[Task]]:
    ticket_id = uuid.UUID("88c61422-84ed-44d0-bfb6-edc98aef8003")
    now = datetime.now(timezone.utc)
    ticket = Ticket(
        id=ticket_id,
        title="E2E Test: Build user dashboard with filters",
        description=(
            "Crear dashboard React con filtros, paginacion, validacion backend, "
            "API, database schema y tests de integracion."
        ),
        status=TicketStatus.pending,
        priority=TicketPriority.P0,
        required_models=["gemini", "claude", "codex"],
        context_snapshot={"version": "1.0"},
        created_at=now,
        updated_at=now,
    )

    frontend = Task(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        name="Frontend React dashboard filters",
        assigned_model=AgentModel.gemini,
        status=TaskStatus.pending,
        dependencies=[],
        prompt_sent=None,
        output=None,
        execution_log=None,
        created_at=now,
        updated_at=now,
    )
    backend = Task(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        name="Backend API filters and pagination",
        assigned_model=AgentModel.claude,
        status=TaskStatus.pending,
        dependencies=[],
        prompt_sent=None,
        output=None,
        execution_log=None,
        created_at=now,
        updated_at=now,
    )
    database = Task(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        name="Database schema for filters",
        assigned_model=AgentModel.claude,
        status=TaskStatus.pending,
        dependencies=[],
        prompt_sent=None,
        output=None,
        execution_log=None,
        created_at=now,
        updated_at=now,
    )
    tests_task = Task(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        name="Integration tests for dashboard flow",
        assigned_model=AgentModel.codex,
        status=TaskStatus.pending,
        dependencies=[frontend.id, backend.id],
        prompt_sent=None,
        output=None,
        execution_log=None,
        created_at=now,
        updated_at=now,
    )

    for task in (frontend, backend, database, tests_task):
        task.ticket = ticket
    ticket.tasks = [frontend, backend, database, tests_task]
    return ticket, ticket.tasks


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        task_id="smart-ticket",
        estimated_total_duration_min=21.8,
        estimated_cost_usd=0.1419,
        components=[
            ComponentAnalysis("Backend API", "parallel", [], 11.2, "claude"),
            ComponentAnalysis("Frontend", "parallel", [], 8.4, "gemini"),
            ComponentAnalysis("Database", "parallel", [], 5.6, "claude"),
            ComponentAnalysis("Tests", "sequential", ["Backend API", "Frontend"], 7.0, "codex"),
        ],
        critical_path_component="Backend API",
        parallel_components=["Backend API", "Frontend", "Database"],
        sequential_components=["Tests"],
        premium_suggestion={"component": "Backend API", "suggested_model": "claude-opus-4-7"},
        timeline_visualization="Timeline",
    )


class StubSmartRouter:
    def __init__(self, responses: list[str] | None = None):
        self.responses = iter(responses or ["B"])
        self.analyze_task = AsyncMock(return_value=_plan())
        self.generate_report = AsyncMock(side_effect=self._generate_report)

    def _format_plan_table(self, plan: ExecutionPlan) -> str:
        return f"PLAN {plan.critical_path_component}"

    async def _user_input_fn(self, _prompt: str) -> str:
        return next(self.responses, "B")

    async def _generate_report(self, _result) -> str:
        await asyncio.sleep(0)
        return (
            "## 1. FALLOS\n"
            "## 2. COSTO + TIEMPO\n"
            "## 3. PARALELIZACION\n"
            "## 4. SUGERENCIAS"
        )


@pytest.mark.asyncio
async def test_load_tasks_from_ticket(mock_db, mock_router, mock_context_manager):
    ticket, tasks = _ticket_with_tasks()
    executor = TaskExecutor(
        db=mock_db,
        router=mock_router,
        context_manager=mock_context_manager,
        smart_router=StubSmartRouter(),
    )
    mock_db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: ticket))

    loaded_ticket, loaded_tasks = await executor._load_ticket_with_tasks(ticket.id)

    assert loaded_ticket is ticket
    assert [task.name for task in loaded_tasks] == [task.name for task in tasks]


@pytest.mark.asyncio
async def test_smart_router_analysis_integration(mock_db, mock_router, mock_context_manager):
    ticket, tasks = _ticket_with_tasks()
    smart_router = StubSmartRouter(["B"])
    executor = TaskExecutor(
        db=mock_db,
        router=mock_router,
        context_manager=mock_context_manager,
        smart_router=smart_router,
    )

    with patch.object(executor, "_load_ticket_with_tasks", AsyncMock(return_value=(ticket, tasks))), patch.object(
        executor,
        "_execute_task_in_isolated_session",
        AsyncMock(side_effect=[
            TaskResult(task_id=tasks[0].id, success=True, model_used="gemini", latency_ms=100),
            TaskResult(task_id=tasks[1].id, success=True, model_used="claude", latency_ms=120),
            TaskResult(task_id=tasks[2].id, success=True, model_used="claude", latency_ms=90),
            TaskResult(task_id=tasks[3].id, success=True, model_used="codex", latency_ms=80),
        ]),
    ):
        report = await executor.execute_ticket_with_smart_routing(ticket.id)

    analyzed_text = smart_router.analyze_task.await_args.args[0]
    assert "Frontend React dashboard filters" in analyzed_text
    assert "Backend API filters and pagination" in analyzed_text
    assert report.plan.critical_path_component == "Backend API"
    assert report.mode == ExecutionMode.AUTOMATED


@pytest.mark.asyncio
async def test_execute_tasks_in_parallel_waves(mock_db, mock_router, mock_context_manager):
    ticket, tasks = _ticket_with_tasks()
    executor = TaskExecutor(
        db=mock_db,
        router=mock_router,
        context_manager=mock_context_manager,
        smart_router=StubSmartRouter(["B"]),
    )
    starts: dict[uuid.UUID, float] = {}
    ends: dict[uuid.UUID, float] = {}

    async def fake_exec(task_id: uuid.UUID) -> TaskResult:
        starts[task_id] = time.monotonic()
        await asyncio.sleep(0.02 if task_id != tasks[3].id else 0.005)
        ends[task_id] = time.monotonic()
        model = next(task.assigned_model.value for task in tasks if task.id == task_id)
        return TaskResult(task_id=task_id, success=True, model_used=model, latency_ms=50)

    with patch.object(executor, "_load_ticket_with_tasks", AsyncMock(return_value=(ticket, tasks))), patch.object(
        executor,
        "_execute_task_in_isolated_session",
        AsyncMock(side_effect=fake_exec),
    ):
        report = await executor.execute_ticket_with_smart_routing(ticket.id)

    first_wave_ids = {tasks[0].id, tasks[1].id, tasks[2].id}
    assert report.success is True
    assert max(starts[task_id] for task_id in first_wave_ids) < ends[tasks[0].id]
    assert starts[tasks[3].id] >= max(ends[task_id] for task_id in first_wave_ids)


@pytest.mark.asyncio
async def test_human_in_the_loop_critical_path(mock_db, mock_router, mock_context_manager):
    ticket, tasks = _ticket_with_tasks()
    executor = TaskExecutor(
        db=mock_db,
        router=mock_router,
        context_manager=mock_context_manager,
        smart_router=StubSmartRouter(["A", "cancelar"]),
    )

    with patch.object(executor, "_load_ticket_with_tasks", AsyncMock(return_value=(ticket, tasks))), patch.object(
        executor,
        "_execute_task_in_isolated_session",
        AsyncMock(),
    ) as execute_mock:
        report = await executor.execute_ticket_with_smart_routing(ticket.id)

    execute_mock.assert_not_awaited()
    assert report.success is False
    assert report.mode == ExecutionMode.HUMAN_IN_THE_LOOP
    assert "critical component rejected by user" in report.failures[0]["error"]


@pytest.mark.asyncio
async def test_execution_report_generation(mock_db, mock_router, mock_context_manager):
    ticket, tasks = _ticket_with_tasks()
    smart_router = StubSmartRouter(["B"])
    executor = TaskExecutor(
        db=mock_db,
        router=mock_router,
        context_manager=mock_context_manager,
        smart_router=smart_router,
    )

    with patch.object(executor, "_load_ticket_with_tasks", AsyncMock(return_value=(ticket, tasks))), patch.object(
        executor,
        "_execute_task_in_isolated_session",
        AsyncMock(side_effect=[
            TaskResult(task_id=tasks[0].id, success=True, model_used="gemini", latency_ms=100),
            TaskResult(task_id=tasks[1].id, success=True, model_used="claude", latency_ms=120),
            TaskResult(task_id=tasks[2].id, success=True, model_used="claude", latency_ms=90),
            TaskResult(task_id=tasks[3].id, success=True, model_used="codex", latency_ms=80),
        ]),
    ):
        report = await executor.execute_ticket_with_smart_routing(ticket.id)

    assert "## 1. FALLOS" in report.report_text
    assert "## 2. COSTO + TIEMPO" in report.report_text
    assert "## 3. PARALELIZACION" in report.report_text
    assert "## 4. SUGERENCIAS" in report.report_text
    assert report.parallelization_breakdown["wave_count"] == 2
    assert set(report.parallelization_breakdown["parallel_components"]) == {
        "Frontend React dashboard filters",
        "Backend API filters and pagination",
        "Database schema for filters",
    }

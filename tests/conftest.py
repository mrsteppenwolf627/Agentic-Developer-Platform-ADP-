from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.litellm_router import ModelRouter, RouteResult
from app.database import get_db
from app.main import app
from app.models.schemas import (
    Adr,
    AdrStatus,
    AgentModel,
    Evaluation,
    EvaluationModel,
    EvaluationType,
    RollbackState,
    Task,
    TaskStatus,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from app.services.context_manager import ContextManager, ContextState


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.value


class RowsResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


@pytest.fixture
def mock_db():
    db = MagicMock(spec=AsyncSession)
    added = []

    def add(obj):
        added.append(obj)

    db.add = MagicMock(side_effect=add)
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.close = AsyncMock()
    db.refresh = AsyncMock()
    db._added = added
    return db


@pytest.fixture
def mock_router():
    router = MagicMock(spec=ModelRouter)
    router.route_task = AsyncMock(
        return_value=RouteResult(
            content="def generated() -> str:\n    return 'ok'\n",
            model_used="claude-sonnet-4-6",
            model_assigned="claude",
            tokens_input=120,
            tokens_output=60,
            tokens_total=180,
            latency_ms=320,
            attempt=1,
            session_id=uuid.uuid4(),
        )
    )
    return router


@pytest.fixture
def mock_context_manager(tmp_path):
    context_path = tmp_path / "CONTEXT.md"
    context_path.write_text(
        "# CONTEXT\n\n## TAREAS EJECUTADAS HOY\n- [ ] **Task #6:** Tests + Deploy -> Completada por [modelo] @ [hora]\n\n## ULTIMA ACTUALIZACION\n- **Fecha:** 2026-04-16 12:30\n- **Por:** Gemini\n- **Cambios:** React dashboard minimo viable\n",
        encoding="utf-8",
    )
    ctx = MagicMock(spec=ContextManager)
    ctx.context_path = context_path
    ctx.snapshot_context = AsyncMock(return_value=uuid.uuid4())
    ctx.restore_context = AsyncMock(return_value=True)
    ctx.get_latest_rollback = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
    ctx.mark_rollback_applied = AsyncMock()
    ctx.load_context = MagicMock(return_value=ContextState(raw_content=context_path.read_text(encoding="utf-8")))
    ctx.update_context = MagicMock()
    ctx.commit_context = MagicMock(return_value="abc1234")
    return ctx


@pytest.fixture
def sample_ticket():
    now = datetime.now(timezone.utc)
    return Ticket(
        id=uuid.uuid4(),
        title="Implement TaskExecutor",
        description="Build the execution service",
        status=TicketStatus.pending,
        priority=TicketPriority.P1,
        required_models=["claude", "codex"],
        context_snapshot={"version": "1.0"},
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def sample_task(sample_ticket):
    now = datetime.now(timezone.utc)
    task = Task(
        id=uuid.uuid4(),
        ticket_id=sample_ticket.id,
        name="Task #6: Tests + Deploy",
        assigned_model=AgentModel.claude,
        status=TaskStatus.pending,
        dependencies=[],
        prompt_sent=None,
        output=None,
        execution_log=None,
        created_at=now,
        updated_at=now,
    )
    task.ticket = sample_ticket
    task.evaluations = []
    task.agent_sessions = []
    task.rollback_entries = []
    return task


@pytest.fixture
def sample_evaluation(sample_task):
    return Evaluation(
        id=uuid.uuid4(),
        task_id=sample_task.id,
        evaluation_type=EvaluationType.security,
        score=0.95,
        findings={"issues": [], "recommendations": [], "raw_output": "ok"},
        passed=True,
        evaluated_by=EvaluationModel.codex,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_adr():
    now = datetime.now(timezone.utc)
    return Adr(
        id=1,
        title="ADR-001 Persistence",
        status=AdrStatus.accepted,
        content="Use PostgreSQL via Supabase.",
        impact_area="database",
        approved_by="Arquitecto",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def client(mock_db):
    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


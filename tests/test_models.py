from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    AdrStatus,
    AgentModel,
    AgentSession,
    Evaluation,
    EvaluationCreate,
    EvaluationModel,
    EvaluationType,
    SessionStatus,
    Task,
    TaskStatus,
    TaskUpdate,
    Ticket,
    TicketCreate,
    TicketPriority,
    TicketStatus,
)


def test_orm_models_can_be_built_in_memory(sample_ticket, sample_task, sample_adr):
    evaluation = Evaluation(
        id=uuid.uuid4(),
        task_id=sample_task.id,
        evaluation_type=EvaluationType.quality,
        score=0.88,
        findings={"issues": [], "recommendations": []},
        passed=True,
        evaluated_by=EvaluationModel.claude,
        created_at=datetime.now(timezone.utc),
    )
    session = AgentSession(
        id=uuid.uuid4(),
        task_id=sample_task.id,
        model_used=AgentModel.claude,
        model_version="claude-sonnet-4-6",
        tokens_used=123,
        latency_ms=456,
        status=SessionStatus.completed,
        error_message=None,
        created_at=datetime.now(timezone.utc),
    )

    assert isinstance(sample_ticket, Ticket)
    assert isinstance(sample_task, Task)
    assert sample_task.ticket_id == sample_ticket.id
    assert evaluation.evaluation_type is EvaluationType.quality
    assert sample_adr.status is AdrStatus.accepted
    assert session.tokens_used == 123


def test_ticket_create_title_is_normalized_by_validator():
    payload = TicketCreate(
        title="  CI pipeline task  ",
        description="Add tests",
        status=TicketStatus.pending,
        priority=TicketPriority.P1,
        required_models=[AgentModel.codex],
    )

    assert payload.title == "CI pipeline task"


def test_ticket_create_rejects_blank_title():
    with pytest.raises(ValidationError):
        TicketCreate(title="   ")


def test_task_update_output_validator_rejects_blank_output():
    with pytest.raises(ValidationError):
        TaskUpdate(output="   ")


def test_evaluation_schema_enforces_score_range(sample_task):
    payload = EvaluationCreate(
        task_id=sample_task.id,
        evaluation_type=EvaluationType.security,
        evaluated_by=EvaluationModel.codex,
        score=0.75,
        findings={"issues": []},
        passed=True,
    )

    assert payload.score == 0.75

    with pytest.raises(ValidationError):
        EvaluationCreate(
            task_id=sample_task.id,
            evaluation_type=EvaluationType.security,
            evaluated_by=EvaluationModel.codex,
            score=1.5,
            findings={},
            passed=False,
        )

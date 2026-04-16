"""FastAPI router — /api/tasks endpoints.

Endpoints:
  POST   /api/tasks/{task_id}/execute   → execute a pending task
  GET    /api/tasks/{task_id}           → task state + execution history
  GET    /api/tasks/ticket/{ticket_id}  → all tasks for a ticket
  POST   /api/tasks/{task_id}/rollback  → restore to pre-execution snapshot

All write operations are transactional: commit on success, rollback on error.
SQL injection protection via ORM (no raw SQL strings with user input).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.schemas import (
    AgentSessionResponse,
    EvaluationResponse,
    RollbackStackResponse,
    RollbackState,
    Task,
    TaskResponse,
    TaskStatus,
    Ticket,
    RollbackStack,
    AgentSession,
    Evaluation,
)
from app.services.context_manager import ContextManager
from app.services.task_executor import TaskExecutor, TaskResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Request / Response schemas for this router
# ---------------------------------------------------------------------------

class ExecuteResponse(BaseModel):
    task_id: uuid.UUID
    success: bool
    output: Optional[str] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    model_used: Optional[str] = None
    tokens_total: int = 0
    latency_ms: int = 0
    attempt: int = 1
    rollback_id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None

    @classmethod
    def from_result(cls, r: TaskResult) -> "ExecuteResponse":
        return cls(
            task_id=r.task_id,
            success=r.success,
            output=r.output,
            error_message=r.error_message,
            error_type=r.error_type,
            model_used=r.model_used,
            tokens_total=r.tokens_total,
            latency_ms=r.latency_ms,
            attempt=r.attempt,
            rollback_id=r.rollback_id,
            session_id=r.session_id,
        )


class TaskDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task: TaskResponse
    evaluations: List[EvaluationResponse] = []
    agent_sessions: List[AgentSessionResponse] = []
    rollback_entries: List[RollbackStackResponse] = []


class RollbackRequest(BaseModel):
    rollback_id: Optional[uuid.UUID] = None  # If None, uses latest active entry


class RollbackResponse(BaseModel):
    task_id: uuid.UUID
    rollback_id: uuid.UUID
    restored: bool
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_task_or_404(task_id: uuid.UUID, db: AsyncSession) -> Task:
    result = await db.execute(
        select(Task)
        .where(Task.id == task_id)
        .options(
            selectinload(Task.evaluations),
            selectinload(Task.agent_sessions),
            selectinload(Task.rollback_entries),
            selectinload(Task.ticket),
        )
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )
    return task


async def _get_ticket_or_404(ticket_id: uuid.UUID, db: AsyncSession) -> Ticket:
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found",
        )
    return ticket


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/{task_id}/execute",
    response_model=ExecuteResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute a pending task",
    description=(
        "Executes the task with its assigned model. "
        "Validates dependencies, snapshots CONTEXT.md, calls the LLM router, "
        "and persists the output. Evaluation (ADR-003) is a separate step."
    ),
)
async def execute_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ExecuteResponse:
    # Verify task exists before spinning up executor
    await _get_task_or_404(task_id, db)

    executor = TaskExecutor(db=db)
    result = await executor.execute_task(task_id)

    if not result.success and result.error_type == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.error_message,
        )

    if not result.success and result.error_type == "invalid_state":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=result.error_message,
        )

    if not result.success and result.error_type == "dependency_unmet":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.error_message,
        )

    # router_error and internal errors → 502 (external model failure, not our bug)
    if not result.success and result.error_type in ("router_error", "timeout", "rate_limit", "api_error"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Model execution failed: {result.error_message}",
        )

    # Unexpected internal failures → 500
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error_message,
        )

    return ExecuteResponse.from_result(result)


@router.get(
    "/{task_id}",
    response_model=TaskDetailResponse,
    summary="Get task detail with full history",
    description="Returns the task state plus all evaluations, agent sessions, and rollback entries.",
)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> TaskDetailResponse:
    task = await _get_task_or_404(task_id, db)

    return TaskDetailResponse(
        task=TaskResponse.model_validate(task),
        evaluations=[EvaluationResponse.model_validate(e) for e in task.evaluations],
        agent_sessions=[AgentSessionResponse.model_validate(s) for s in task.agent_sessions],
        rollback_entries=[RollbackStackResponse.model_validate(r) for r in task.rollback_entries],
    )


@router.get(
    "/ticket/{ticket_id}",
    response_model=List[TaskResponse],
    summary="List all tasks for a ticket",
    description="Returns tasks ordered by creation time.",
)
async def list_tasks_by_ticket(
    ticket_id: uuid.UUID,
    status_filter: Optional[TaskStatus] = None,
    db: AsyncSession = Depends(get_db),
) -> List[TaskResponse]:
    # Verify ticket exists
    await _get_ticket_or_404(ticket_id, db)

    stmt = select(Task).where(Task.ticket_id == ticket_id)
    if status_filter is not None:
        stmt = stmt.where(Task.status == status_filter)
    stmt = stmt.order_by(Task.created_at.asc())

    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return [TaskResponse.model_validate(t) for t in tasks]


@router.post(
    "/{task_id}/rollback",
    response_model=RollbackResponse,
    summary="Restore task context to pre-execution snapshot",
    description=(
        "Restores CONTEXT.md to the state captured before the task ran. "
        "If rollback_id is omitted, uses the most recent active snapshot. "
        "Idempotent — safe to call multiple times."
    ),
)
async def rollback_task(
    task_id: uuid.UUID,
    body: RollbackRequest,
    db: AsyncSession = Depends(get_db),
) -> RollbackResponse:
    task = await _get_task_or_404(task_id, db)
    ctx = ContextManager()

    rollback_id = body.rollback_id

    # If no specific rollback_id provided, find the latest active entry
    if rollback_id is None:
        latest = await ctx.get_latest_rollback(task_id=task_id, db=db)
        if latest is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active rollback snapshot found for task {task_id}",
            )
        rollback_id = latest.id

    restored = await ctx.restore_context(rollback_id=rollback_id, db=db)

    if not restored:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rollback entry {rollback_id} not found or already applied",
        )

    # If task is failed, reset to pending so it can be retried
    if task.status == TaskStatus.failed:
        task.status = TaskStatus.pending
        logger.info(
            "rollback_task | task=%s reset pending after rollback", task_id
        )

    return RollbackResponse(
        task_id=task_id,
        rollback_id=rollback_id,
        restored=restored,
        message=(
            "CONTEXT.md restored to pre-execution snapshot. "
            "Task reset to 'pending' and can be re-executed."
            if task.status == TaskStatus.pending
            else "CONTEXT.md restored to pre-execution snapshot."
        ),
    )

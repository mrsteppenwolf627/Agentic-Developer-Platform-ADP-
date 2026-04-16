"""TaskExecutor — orchestrates task execution across agent models.

Execution flow (ADR-002, ADR-003):

  1. Load task + validate state (pending only, no double-execution)
  2. Check dependency chain (all deps must be 'completed')
  3. Snapshot CONTEXT.md → rollback_stack (ADR-003)
  4. Set task.status = 'in_progress'
  5. Build prompt via PromptBuilder with CONTEXT.md injection
  6. Call ModelRouter.route_task() — handles fallback + agent_sessions log
  7. Persist output + execution_log to task record
  8. If execution fails → restore rollback + set task.status = 'failed'
  9. Evaluation happens AFTER this (Evaluation Framework — Task #4).
     TaskExecutor returns TaskResult with success=True only after LLM call.
     Status transitions to 'completed' are the responsibility of the
     EvaluationFramework once all gates pass (ADR-003).

Usage:
    executor = TaskExecutor(db=session, router=get_router())
    result = await executor.execute_task(task_id)
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.litellm_router import ModelRouter, ModelRouterError, get_router
from app.agents.prompts import PromptBuilder
from app.models.schemas import (
    AgentModel,
    Task,
    TaskStatus,
    Ticket,
)
from app.services.context_manager import ContextManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class TaskResult:
    """Result of a single task execution attempt."""
    task_id: uuid.UUID
    success: bool
    output: Optional[str] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None   # dependency_unmet | invalid_state | router_error | internal
    model_used: Optional[str] = None
    tokens_total: int = 0
    latency_ms: int = 0
    attempt: int = 1
    rollback_id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None


# ---------------------------------------------------------------------------
# Dependency resolution
# ---------------------------------------------------------------------------

async def _resolve_dependencies(
    task: Task,
    db: AsyncSession,
) -> list[uuid.UUID]:
    """Return list of dependency task IDs that are NOT yet completed.

    Returns an empty list when all dependencies are satisfied (safe to proceed).
    """
    if not task.dependencies:
        return []

    result = await db.execute(
        select(Task.id, Task.status).where(Task.id.in_(task.dependencies))
    )
    rows = result.all()

    # Tasks that exist but are not completed
    unresolved = [
        row.id for row in rows
        if row.status != TaskStatus.completed
    ]

    # Dependencies that don't exist in DB at all (treat as blocking)
    found_ids = {row.id for row in rows}
    missing = [dep_id for dep_id in task.dependencies if dep_id not in found_ids]
    unresolved.extend(missing)

    return unresolved


# ---------------------------------------------------------------------------
# TaskExecutor
# ---------------------------------------------------------------------------

class TaskExecutor:
    """Orchestrates a single task execution with full lifecycle management.

    Args:
        db:      AsyncSession for all DB operations.
        router:  ModelRouter instance (defaults to module singleton).
        context_manager: ContextManager (defaults to project-root CONTEXT.md).
    """

    def __init__(
        self,
        db: AsyncSession,
        router: Optional[ModelRouter] = None,
        context_manager: Optional[ContextManager] = None,
    ) -> None:
        self.db = db
        self.router = router or get_router()
        self.ctx = context_manager or ContextManager()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute_task(self, task_id: uuid.UUID) -> TaskResult:
        """Execute a task end-to-end.

        Returns a TaskResult regardless of success/failure — never raises.
        Callers should check TaskResult.success.
        """
        logger.info("execute_task | task=%s START", task_id)

        # ----------------------------------------------------------
        # 1. Load task with ticket relationship
        # ----------------------------------------------------------
        task = await self._load_task(task_id)
        if task is None:
            logger.error("execute_task | task=%s NOT FOUND", task_id)
            return TaskResult(
                task_id=task_id,
                success=False,
                error_message=f"Task {task_id} not found",
                error_type="not_found",
            )

        # ----------------------------------------------------------
        # 2. Validate task state (idempotency guard)
        # ----------------------------------------------------------
        if task.status not in (TaskStatus.pending,):
            logger.warning(
                "execute_task | task=%s invalid_state=%s (expected pending)",
                task_id, task.status,
            )
            return TaskResult(
                task_id=task_id,
                success=False,
                error_message=(
                    f"Task is in state '{task.status.value}', expected 'pending'. "
                    "Cannot re-execute a task that is in_progress, completed, or failed."
                ),
                error_type="invalid_state",
            )

        # ----------------------------------------------------------
        # 3. Check dependency chain
        # ----------------------------------------------------------
        unresolved = await _resolve_dependencies(task, self.db)
        if unresolved:
            logger.warning(
                "execute_task | task=%s blocked_by=%s",
                task_id, unresolved,
            )
            return TaskResult(
                task_id=task_id,
                success=False,
                error_message=(
                    f"Task has {len(unresolved)} unresolved dependencies: "
                    f"{[str(u) for u in unresolved]}"
                ),
                error_type="dependency_unmet",
            )

        # ----------------------------------------------------------
        # 4. Snapshot CONTEXT.md → rollback_stack (ADR-003 mandate)
        # ----------------------------------------------------------
        rollback_id: Optional[uuid.UUID] = None
        try:
            rollback_id = await self.ctx.snapshot_context(
                task_id=task_id, db=self.db
            )
        except Exception as exc:
            logger.error("execute_task | task=%s snapshot_failed: %s", task_id, exc)
            # Snapshot failure is non-blocking for now but logged prominently
            # In production: uncomment return to enforce strict snapshot policy
            # return TaskResult(task_id=task_id, success=False,
            #                   error_message=str(exc), error_type="snapshot_failed")

        # ----------------------------------------------------------
        # 5. Transition task → in_progress
        # ----------------------------------------------------------
        task.status = TaskStatus.in_progress
        await self.db.flush()

        # ----------------------------------------------------------
        # 6. Build structured prompt
        # ----------------------------------------------------------
        context_state = self._load_context_safe()
        prompt_builder = PromptBuilder(context_md=context_state.raw_content)

        system_prompt, user_prompt = prompt_builder.build(
            model_key=task.assigned_model.value,
            task_name=task.name,
            instructions=self._build_instructions(task),
            prior_output=None,
        )

        # Record the prompt that was sent (for audit trail)
        task.prompt_sent = user_prompt
        await self.db.flush()

        # ----------------------------------------------------------
        # 7. Execute via ModelRouter (handles fallback + session logging)
        # ----------------------------------------------------------
        try:
            route_result = await self.router.route_task(
                task_id=task_id,
                model_assigned=task.assigned_model.value,
                prompt=user_prompt,
                system_prompt=system_prompt,
                db=self.db,
            )
        except ModelRouterError as exc:
            return await self._handle_execution_failure(
                task=task,
                rollback_id=rollback_id,
                error_message=str(exc),
                error_type=exc.details.error_type,
            )
        except Exception as exc:
            return await self._handle_execution_failure(
                task=task,
                rollback_id=rollback_id,
                error_message=str(exc),
                error_type="internal",
            )

        # ----------------------------------------------------------
        # 8. Persist output + execution_log
        #    (status stays 'in_progress' until EvaluationFramework runs)
        # ----------------------------------------------------------
        now = datetime.now(timezone.utc)
        task.output = route_result.content
        task.execution_log = {
            "steps": [
                {
                    "step": "llm_call",
                    "model": route_result.model_used,
                    "attempt": route_result.attempt,
                    "tokens_input": route_result.tokens_input,
                    "tokens_output": route_result.tokens_output,
                    "latency_ms": route_result.latency_ms,
                    "timestamp": now.isoformat(),
                }
            ],
            "errors": [],
            "timing": {
                "completed_at": now.isoformat(),
                "latency_ms": route_result.latency_ms,
            },
        }
        await self.db.flush()

        # ----------------------------------------------------------
        # 9. Record the after-state in rollback_stack
        # ----------------------------------------------------------
        if rollback_id:
            try:
                after_content = self.ctx.context_path.read_text(encoding="utf-8")
                await self.ctx.mark_rollback_applied(
                    rollback_id=rollback_id,
                    context_md_after=after_content,
                    db=self.db,
                )
            except Exception as exc:
                logger.warning("execute_task | task=%s mark_rollback failed: %s", task_id, exc)

        logger.info(
            "execute_task | task=%s SUCCESS model=%s tokens=%d latency=%dms attempt=%d",
            task_id,
            route_result.model_used,
            route_result.tokens_total,
            route_result.latency_ms,
            route_result.attempt,
        )

        return TaskResult(
            task_id=task_id,
            success=True,
            output=route_result.content,
            model_used=route_result.model_used,
            tokens_total=route_result.tokens_total,
            latency_ms=route_result.latency_ms,
            attempt=route_result.attempt,
            rollback_id=rollback_id,
            session_id=route_result.session_id,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _load_task(self, task_id: uuid.UUID) -> Optional[Task]:
        result = await self.db.execute(
            select(Task)
            .where(Task.id == task_id)
            .options(selectinload(Task.ticket))
        )
        return result.scalar_one_or_none()

    def _load_context_safe(self):
        """Load CONTEXT.md; return a stub state if file is unavailable."""
        try:
            return self.ctx.load_context()
        except FileNotFoundError:
            from app.services.context_manager import ContextState
            logger.warning("CONTEXT.md not found; using empty context state")
            return ContextState(raw_content="No CONTEXT.md available.")

    @staticmethod
    def _build_instructions(task: Task) -> str:
        """Build the task-specific instruction block from task metadata."""
        lines = [f"Task name: {task.name}"]

        if task.ticket and task.ticket.description:
            lines.append(f"\nTicket description:\n{task.ticket.description}")

        if task.ticket and task.ticket.title:
            lines.append(f"\nTicket title: {task.ticket.title}")

        lines.append(
            f"\nAssigned to: {task.assigned_model.value} agent. "
            "Implement the full, production-ready solution as described."
        )
        return "\n".join(lines)

    async def _handle_execution_failure(
        self,
        task: Task,
        rollback_id: Optional[uuid.UUID],
        error_message: str,
        error_type: str,
    ) -> TaskResult:
        """Transition task to failed state and trigger rollback."""
        logger.error(
            "execute_task | task=%s FAILED error_type=%s msg=%s",
            task.id, error_type, error_message,
        )

        # Update execution log with error
        task.execution_log = task.execution_log or {"steps": [], "errors": [], "timing": {}}
        task.execution_log["errors"].append(
            {"error_type": error_type, "message": error_message}
        )
        task.status = TaskStatus.failed
        await self.db.flush()

        # Restore CONTEXT.md snapshot (ADR-003: no partial states)
        if rollback_id:
            try:
                restored = await self.ctx.restore_context(rollback_id, self.db)
                if restored:
                    logger.info(
                        "execute_task | task=%s rollback_id=%s CONTEXT RESTORED",
                        task.id, rollback_id,
                    )
            except Exception as exc:
                logger.error(
                    "execute_task | task=%s ROLLBACK FAILED: %s", task.id, exc
                )

        return TaskResult(
            task_id=task.id,
            success=False,
            error_message=error_message,
            error_type=error_type,
            rollback_id=rollback_id,
        )

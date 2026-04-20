"""TaskExecutor - orchestrates task execution across agent models.

Execution flow (ADR-002, ADR-003):

  1. Load task + validate state (pending only, no double-execution)
  2. Check dependency chain (all deps must be 'completed')
  3. Snapshot CONTEXT.md -> rollback_stack (ADR-003)
  4. Set task.status = 'in_progress'
  5. Build prompt via PromptBuilder with CONTEXT.md injection
  6. Call ModelRouter.route_task() - handles fallback + agent_sessions log
  7. Persist output + execution_log to task record
  8. If execution fails -> restore rollback + set task.status = 'failed'
  9. Evaluation happens AFTER this (Evaluation Framework - Task #4).
     TaskExecutor returns TaskResult with success=True only after LLM call.
     Status transitions to 'completed' are the responsibility of the
     EvaluationFramework once all gates pass (ADR-003).

Usage:
    executor = TaskExecutor(db=session, router=get_router())
    result = await executor.execute_task(task_id)
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.litellm_router import ModelRouter, ModelRouterError, get_router
from app.agents.prompts import PromptBuilder
from app.agents.smart_router import (
    ComponentResult,
    ExecutionMode,
    ExecutionPlan,
    ExecutionResult,
    SmartRouter,
)
from app.database import AsyncSessionLocal
from app.models.schemas import Task, TaskStatus, Ticket
from app.services.context_manager import ContextManager

logger = logging.getLogger(__name__)


_TASK_COST_USD: dict[str, float] = {
    "claude": 0.051,
    "gemini": 0.0049,
    "codex": 0.035,
}


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
    error_type: Optional[str] = None  # dependency_unmet | invalid_state | router_error | internal
    model_used: Optional[str] = None
    tokens_total: int = 0
    latency_ms: int = 0
    attempt: int = 1
    rollback_id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None


@dataclass
class ExecutionReport:
    """Aggregated execution report for ticket-level smart routing."""

    ticket_id: uuid.UUID
    mode: ExecutionMode
    success: bool
    plan: ExecutionPlan
    task_results: list[TaskResult] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    parallelization_breakdown: dict[str, Any] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)
    actual_duration_min: float = 0.0
    actual_cost_usd: float = 0.0
    execution_log: str = ""
    report_text: str = ""


# ---------------------------------------------------------------------------
# Dependency resolution
# ---------------------------------------------------------------------------


async def _resolve_dependencies(
    task: Task,
    db: AsyncSession,
) -> list[uuid.UUID]:
    """Return list of dependency task IDs that are NOT yet completed."""
    if not task.dependencies:
        return []

    result = await db.execute(
        select(Task.id, Task.status).where(Task.id.in_(task.dependencies))
    )
    rows = result.all()

    unresolved = [row.id for row in rows if row.status != TaskStatus.completed]
    found_ids = {row.id for row in rows}
    missing = [dep_id for dep_id in task.dependencies if dep_id not in found_ids]
    unresolved.extend(missing)
    return unresolved


# ---------------------------------------------------------------------------
# TaskExecutor
# ---------------------------------------------------------------------------


class TaskExecutor:
    """Orchestrates task execution with optional SmartRouter ticket batching."""

    def __init__(
        self,
        db: AsyncSession,
        router: Optional[ModelRouter] = None,
        context_manager: Optional[ContextManager] = None,
        smart_router: Optional[SmartRouter] = None,
        session_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.db = db
        self.router = router or get_router()
        self.ctx = context_manager or ContextManager()
        self.smart_router = smart_router or SmartRouter()
        self.session_factory = session_factory or AsyncSessionLocal

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute_task(self, task_id: uuid.UUID) -> TaskResult:
        """Execute a task end-to-end without raising."""
        logger.info("execute_task | task=%s START", task_id)
        task, validation_error = await self._load_and_validate_task(task_id)
        if validation_error:
            return validation_error
        assert task is not None
        return await self._execute_task_internal(task)

    async def execute_ticket_with_smart_routing(
        self,
        ticket_id: uuid.UUID,
        mode: ExecutionMode = ExecutionMode.HUMAN_IN_THE_LOOP,
    ) -> ExecutionReport:
        """
        1. Load all ticket tasks
        2. Combine descriptions and analyze with SmartRouter
        3. Show plan and choose mode
        4. If HitL: ask approval only for the critical wave
        5. Execute tasks in parallel by dependency waves
        6. Return ExecutionReport
        """
        start_ts = time.monotonic()
        ticket, tasks = await self._load_ticket_with_tasks(ticket_id)
        if ticket is None:
            empty_plan = await self.smart_router.analyze_task(f"ticket {ticket_id} not found")
            failure = {
                "component": "Ticket",
                "error": f"Ticket {ticket_id} not found",
                "recovery": "verify ticket_id and retry",
            }
            execution_result = ExecutionResult(
                success=False,
                actual_duration_min=0.0,
                actual_cost_usd=0.0,
                failures=[failure],
                parallelization_breakdown={
                    "parallel_components": [],
                    "sequential_components": [],
                    "models_used": [],
                    "time_saved_min": 0.0,
                    "estimated_total_min": 0.0,
                    "estimated_cost_usd": 0.0,
                },
                execution_log=f"ticket={ticket_id} not found",
                suggestions=["Crea tasks para el ticket antes de ejecutar SmartRouter."],
            )
            return ExecutionReport(
                ticket_id=ticket_id,
                mode=mode,
                success=False,
                plan=empty_plan,
                failures=[failure],
                suggestions=execution_result.suggestions,
                report_text=await self.smart_router.generate_report(execution_result),
            )

        analysis_text = self._build_ticket_analysis_text(ticket, tasks)
        plan = await self.smart_router.analyze_task(analysis_text)
        selected_mode = await self._select_execution_mode(plan, default=mode)
        waves = self._build_task_waves(tasks)
        critical_wave_index = self._find_critical_wave_index(plan, waves)

        task_results: list[TaskResult] = []
        failures: list[dict[str, Any]] = []
        log_lines = [
            f"[{datetime.now(timezone.utc).isoformat()}] start | ticket={ticket_id} mode={selected_mode.value}"
        ]

        for wave_index, wave in enumerate(waves):
            if (
                selected_mode == ExecutionMode.HUMAN_IN_THE_LOOP
                and wave_index == critical_wave_index
            ):
                approved = await self._approve_critical_wave(plan, wave, wave_index)
                if not approved:
                    log_lines.append(f"critical wave {wave_index + 1} rejected by user")
                    failures.append(
                        {
                            "component": plan.critical_path_component,
                            "error": "critical component rejected by user",
                            "recovery": "approve the critical wave to continue execution",
                        }
                    )
                    break

            wave_task_ids = [task.id for task in wave]
            log_lines.append(f"wave {wave_index + 1}/{len(waves)} -> {[task.name for task in wave]}")

            results = await asyncio.gather(
                *(self._execute_task_in_isolated_session(task_id) for task_id in wave_task_ids),
                return_exceptions=True,
            )

            for task, result in zip(wave, results):
                if isinstance(result, BaseException):
                    failures.append(
                        {
                            "component": task.name,
                            "error": str(result),
                            "recovery": "task crashed before producing a TaskResult",
                        }
                    )
                    task_results.append(
                        TaskResult(
                            task_id=task.id,
                            success=False,
                            error_message=str(result),
                            error_type="internal",
                            model_used=task.assigned_model.value,
                        )
                    )
                    log_lines.append(f"  x {task.name}: {result}")
                else:
                    task_results.append(result)
                    if result.success:
                        log_lines.append(
                            f"  ok {task.name} model={result.model_used} latency={result.latency_ms}ms"
                        )
                    else:
                        failures.append(
                            {
                                "component": task.name,
                                "error": result.error_message or "unknown",
                                "recovery": "inspect dependency state or router failure",
                            }
                        )
                        log_lines.append(
                            f"  x {task.name}: {result.error_type} {result.error_message}"
                        )

            if any(not r.success for r in task_results if r.task_id in wave_task_ids):
                log_lines.append("stopping after failed wave")
                break

        actual_duration = round((time.monotonic() - start_ts) / 60.0, 3)
        actual_cost = round(
            sum(self._estimate_task_cost_usd(r.model_used) for r in task_results if r.success),
            4,
        )
        breakdown = self._build_ticket_parallelization_breakdown(plan, waves, tasks, task_results)
        suggestions = self._generate_ticket_suggestions(plan, task_results, failures)
        success = len(failures) == 0 and len(task_results) == len(tasks)
        log_lines.append(
            f"[{datetime.now(timezone.utc).isoformat()}] end | success={success} duration={actual_duration}min"
        )

        smart_result = ExecutionResult(
            success=success,
            actual_duration_min=actual_duration,
            actual_cost_usd=actual_cost,
            failures=failures,
            parallelization_breakdown=breakdown,
            execution_log="\n".join(log_lines),
            suggestions=suggestions,
        )
        report_text = await self.smart_router.generate_report(smart_result)

        return ExecutionReport(
            ticket_id=ticket_id,
            mode=selected_mode,
            success=success,
            plan=plan,
            task_results=task_results,
            failures=failures,
            parallelization_breakdown=breakdown,
            suggestions=suggestions,
            actual_duration_min=actual_duration,
            actual_cost_usd=actual_cost,
            execution_log=smart_result.execution_log,
            report_text=report_text,
        )

    async def evaluate_task_output(
        self,
        task_id: uuid.UUID,
        output_code: Optional[str] = None,
    ):
        """Run the post-execution governance gate for a task."""
        from app.services.evaluation_engine import EvaluationEngine

        task = await self._load_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        code_to_evaluate = output_code or task.output
        if not code_to_evaluate:
            raise ValueError(f"Task {task_id} has no output to evaluate")

        engine = EvaluationEngine(db=self.db, context_manager=self.ctx)
        return await engine.evaluate_task_output(task_id=task_id, output_code=code_to_evaluate)

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

    async def _load_ticket_with_tasks(
        self,
        ticket_id: uuid.UUID,
    ) -> tuple[Optional[Ticket], list[Task]]:
        result = await self.db.execute(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(selectinload(Ticket.tasks))
        )
        ticket = result.scalar_one_or_none()
        if ticket is None:
            return None, []
        ordered_tasks = sorted(ticket.tasks, key=lambda task: task.created_at)
        return ticket, ordered_tasks

    async def _load_and_validate_task(
        self,
        task_id: uuid.UUID,
    ) -> tuple[Optional[Task], Optional[TaskResult]]:
        task = await self._load_task(task_id)
        if task is None:
            logger.error("execute_task | task=%s NOT FOUND", task_id)
            return None, TaskResult(
                task_id=task_id,
                success=False,
                error_message=f"Task {task_id} not found",
                error_type="not_found",
            )

        if task.status not in (TaskStatus.pending,):
            logger.warning(
                "execute_task | task=%s invalid_state=%s (expected pending)",
                task_id,
                task.status,
            )
            return None, TaskResult(
                task_id=task_id,
                success=False,
                error_message=(
                    f"Task is in state '{task.status.value}', expected 'pending'. "
                    "Cannot re-execute a task that is in_progress, completed, or failed."
                ),
                error_type="invalid_state",
            )

        unresolved = await _resolve_dependencies(task, self.db)
        if unresolved:
            logger.warning("execute_task | task=%s blocked_by=%s", task_id, unresolved)
            return None, TaskResult(
                task_id=task_id,
                success=False,
                error_message=(
                    f"Task has {len(unresolved)} unresolved dependencies: "
                    f"{[str(u) for u in unresolved]}"
                ),
                error_type="dependency_unmet",
            )

        return task, None

    async def _execute_task_internal(self, task: Task) -> TaskResult:
        rollback_id: Optional[uuid.UUID] = None
        try:
            rollback_id = await self.ctx.snapshot_context(task_id=task.id, db=self.db)
        except Exception as exc:
            logger.error("execute_task | task=%s snapshot_failed: %s", task.id, exc)

        task.status = TaskStatus.in_progress
        await self.db.flush()

        context_state = self._load_context_safe()
        prompt_builder = PromptBuilder(context_md=context_state.raw_content)
        system_prompt, user_prompt = prompt_builder.build(
            model_key=task.assigned_model.value,
            task_name=task.name,
            instructions=self._build_instructions(task),
            prior_output=None,
        )

        task.prompt_sent = user_prompt
        await self.db.flush()

        try:
            route_result = await self.router.route_task(
                task_id=task.id,
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

        if rollback_id:
            try:
                after_content = self.ctx.context_path.read_text(encoding="utf-8")
                await self.ctx.mark_rollback_applied(
                    rollback_id=rollback_id,
                    context_md_after=after_content,
                    db=self.db,
                )
            except Exception as exc:
                logger.warning("execute_task | task=%s mark_rollback failed: %s", task.id, exc)

        logger.info(
            "execute_task | task=%s SUCCESS model=%s tokens=%d latency=%dms attempt=%d",
            task.id,
            route_result.model_used,
            route_result.tokens_total,
            route_result.latency_ms,
            route_result.attempt,
        )
        return TaskResult(
            task_id=task.id,
            success=True,
            output=route_result.content,
            model_used=route_result.model_used,
            tokens_total=route_result.tokens_total,
            latency_ms=route_result.latency_ms,
            attempt=route_result.attempt,
            rollback_id=rollback_id,
            session_id=route_result.session_id,
        )

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
            task.id,
            error_type,
            error_message,
        )

        task.execution_log = task.execution_log or {"steps": [], "errors": [], "timing": {}}
        task.execution_log["errors"].append({"error_type": error_type, "message": error_message})
        task.status = TaskStatus.failed
        await self.db.flush()

        if rollback_id:
            try:
                restored = await self.ctx.restore_context(rollback_id, self.db)
                if restored:
                    logger.info(
                        "execute_task | task=%s rollback_id=%s CONTEXT RESTORED",
                        task.id,
                        rollback_id,
                    )
            except Exception as exc:
                logger.error("execute_task | task=%s ROLLBACK FAILED: %s", task.id, exc)

        return TaskResult(
            task_id=task.id,
            success=False,
            error_message=error_message,
            error_type=error_type,
            rollback_id=rollback_id,
        )

    def _build_ticket_analysis_text(self, ticket: Ticket, tasks: list[Task]) -> str:
        task_lines = [
            (
                f"- Task: {task.name} | model={task.assigned_model.value} "
                f"| dependencies={len(task.dependencies or [])}"
            )
            for task in tasks
        ]
        return "\n".join(
            [
                f"Ticket ID: {ticket.id}",
                f"Title: {ticket.title}",
                f"Description: {ticket.description or ''}",
                "Tasks:",
                *task_lines,
            ]
        )

    async def _select_execution_mode(
        self,
        plan: ExecutionPlan,
        default: ExecutionMode,
    ) -> ExecutionMode:
        print(self._console_safe(self.smart_router._format_plan_table(plan)))
        try:
            choice = await self.smart_router._user_input_fn(
                "\nEjecucion: (A) Human-in-the-Loop  (B) Automatizado -> "
            )
        except Exception:
            return default

        selected = choice.strip().upper()
        if selected == "A":
            return ExecutionMode.HUMAN_IN_THE_LOOP
        if selected == "B":
            return ExecutionMode.AUTOMATED
        return default

    async def _approve_critical_wave(
        self,
        plan: ExecutionPlan,
        wave: list[Task],
        wave_index: int,
    ) -> bool:
        prompt = (
            f"\n[HitL] Wave critica {wave_index + 1} para '{plan.critical_path_component}' "
            f"({[task.name for task in wave]}). Ejecutar? (y/cancelar) -> "
        )
        approval = await self.smart_router._user_input_fn(prompt)
        return approval.strip().lower() in ("y", "yes", "s", "si")

    def _build_task_waves(self, tasks: list[Task]) -> list[list[Task]]:
        remaining = {task.id: task for task in tasks}
        completed: set[uuid.UUID] = set()
        task_ids = set(remaining)
        waves: list[list[Task]] = []

        while remaining:
            wave = [
                task
                for task in remaining.values()
                if all(dep in completed or dep not in task_ids for dep in (task.dependencies or []))
            ]
            if not wave:
                logger.warning("execute_ticket_with_smart_routing | circular deps detected")
                wave = list(remaining.values())
            for task in wave:
                completed.add(task.id)
                del remaining[task.id]
            waves.append(sorted(wave, key=lambda item: item.created_at))
        return waves

    def _find_critical_wave_index(
        self,
        plan: ExecutionPlan,
        waves: list[list[Task]],
    ) -> int:
        critical_component = plan.critical_path_component.lower()
        for idx, wave in enumerate(waves):
            if any(self._classify_task_component(task).lower() == critical_component for task in wave):
                return idx
        return 0

    async def _execute_task_in_isolated_session(self, task_id: uuid.UUID) -> TaskResult:
        async with self.session_factory() as session:
            executor = TaskExecutor(
                db=session,
                router=self.router,
                context_manager=self.ctx,
                smart_router=self.smart_router,
                session_factory=self.session_factory,
            )
            result = await executor.execute_task(task_id)
            if hasattr(session, "commit"):
                await session.commit()
            return result

    def _build_ticket_parallelization_breakdown(
        self,
        plan: ExecutionPlan,
        waves: list[list[Task]],
        tasks: list[Task],
        task_results: list[TaskResult],
    ) -> dict[str, Any]:
        result_map = {result.task_id: result for result in task_results}
        serial_minutes = sum(result.latency_ms / 60000.0 for result in task_results if result.success)
        parallel_minutes = sum(
            max((result_map[task.id].latency_ms / 60000.0 for task in wave if task.id in result_map), default=0.0)
            for wave in waves
        )
        parallel_components = [
            task.name
            for wave in waves[:1]
            for task in wave
        ]
        sequential_components = [
            task.name
            for wave in waves[1:]
            for task in wave
        ]
        models_used = sorted({result.model_used for result in task_results if result.model_used})

        return {
            "parallel_components": parallel_components,
            "sequential_components": sequential_components,
            "models_used": models_used,
            "time_saved_min": round(max(0.0, serial_minutes - parallel_minutes), 3),
            "estimated_total_min": plan.estimated_total_duration_min,
            "estimated_cost_usd": plan.estimated_cost_usd,
            "task_count": len(tasks),
            "wave_count": len(waves),
        }

    def _generate_ticket_suggestions(
        self,
        plan: ExecutionPlan,
        task_results: list[TaskResult],
        failures: list[dict[str, Any]],
    ) -> list[str]:
        suggestions: list[str] = []
        if failures:
            suggestions.append("Revisa la wave fallida antes de reintentar la ejecucion completa.")
        if plan.premium_suggestion:
            suggestions.append(
                f"Considera {plan.premium_suggestion['suggested_model']} para {plan.premium_suggestion['component']}."
            )
        if len(plan.parallel_components) < 2:
            suggestions.append("Descompone el ticket en mas tasks independientes para ganar paralelizacion.")
        if not suggestions and task_results:
            suggestions.append("Sin sugerencias adicionales.")
        return suggestions

    def _classify_task_component(self, task: Task) -> str:
        text = f"{task.name} {task.ticket.title if task.ticket else ''} {task.ticket.description if task.ticket else ''}".lower()
        if any(word in text for word in ("frontend", "react", "ui", "dashboard")):
            return "Frontend"
        if any(word in text for word in ("database", "db", "schema", "migration", "sql")):
            return "Database"
        if any(word in text for word in ("test", "pytest", "e2e", "integration")):
            return "Tests"
        if any(word in text for word in ("doc", "swagger", "readme", "openapi")):
            return "Documentation"
        return "Backend API"

    @staticmethod
    def _estimate_task_cost_usd(model_used: Optional[str]) -> float:
        if not model_used:
            return 0.0
        return _TASK_COST_USD.get(model_used, 0.0)

    @staticmethod
    def _console_safe(text: str) -> str:
        return text.encode("cp1252", errors="replace").decode("cp1252")

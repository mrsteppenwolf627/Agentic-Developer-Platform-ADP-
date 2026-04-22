"""FastAPI router for multi-layer evaluation governance."""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.security import get_current_user
from app.evaluators import Finding
from app.models.schemas import Evaluation, Task, User
from app.services.evaluation_engine import EvaluationResult
from app.services.task_executor import TaskExecutor

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


class EvaluateTaskRequest(BaseModel):
    output_code: Optional[str] = Field(
        default=None,
        description="Optional override. If omitted, uses the persisted task.output.",
    )


class PillarSummaryResponse(BaseModel):
    pillar: str
    passed: bool
    score: float
    findings: List[Finding]


class EvaluationSummaryResponse(BaseModel):
    task_id: uuid.UUID
    passed: bool
    score: float
    findings: List[Finding]
    pillars: List[PillarSummaryResponse]


async def _get_task_or_404(task_id: uuid.UUID, db: AsyncSession) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )
    return task


def _to_summary(result: EvaluationResult) -> EvaluationSummaryResponse:
    return EvaluationSummaryResponse(
        task_id=result.task_id,
        passed=result.passed,
        score=result.score,
        findings=result.findings,
        pillars=[
            PillarSummaryResponse(
                pillar=pillar.pillar,
                passed=pillar.passed,
                score=pillar.score,
                findings=pillar.findings,
            )
            for pillar in result.pillars
        ],
    )


@router.post(
    "/{task_id}",
    response_model=EvaluationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate generated task output and apply governance outcome",
)
async def evaluate_task(
    task_id: uuid.UUID,
    body: EvaluateTaskRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> EvaluationSummaryResponse:
    task = await _get_task_or_404(task_id, db)
    output_code = body.output_code or task.output
    if not output_code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Task has no output to evaluate",
        )

    executor = TaskExecutor(db=db)
    result = await executor.evaluate_task_output(task_id=task_id, output_code=output_code)
    return _to_summary(result)


@router.get(
    "/{task_id}",
    response_model=EvaluationSummaryResponse,
    summary="Get aggregated evaluation findings and score for a task",
)
async def get_evaluation(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> EvaluationSummaryResponse:
    await _get_task_or_404(task_id, db)

    result = await db.execute(
        select(Evaluation)
        .where(Evaluation.task_id == task_id)
        .order_by(Evaluation.created_at.asc())
    )
    evaluations = result.scalars().all()
    if not evaluations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No evaluations found for task {task_id}",
        )

    findings: List[Finding] = []
    pillars: List[PillarSummaryResponse] = []
    passed = True
    score_total = 0.0
    for evaluation in evaluations:
        issues = evaluation.findings.get("issues", []) if evaluation.findings else []
        issue_models = [Finding.model_validate(issue) for issue in issues]
        pillar_name = (
            evaluation.findings.get("pillar", evaluation.evaluation_type.value.upper())
            if evaluation.findings
            else evaluation.evaluation_type.value.upper()
        )
        pillars.append(
            PillarSummaryResponse(
                pillar=pillar_name,
                passed=evaluation.passed,
                score=evaluation.score or 0.0,
                findings=issue_models,
            )
        )
        findings.extend(issue_models)
        passed = passed and evaluation.passed
        score_total += evaluation.score or 0.0

    return EvaluationSummaryResponse(
        task_id=task_id,
        passed=passed,
        score=round(score_total / len(evaluations), 2),
        findings=findings,
        pillars=pillars,
    )

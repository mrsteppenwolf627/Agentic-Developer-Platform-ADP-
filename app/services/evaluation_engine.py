"""Mandatory multi-layer evaluation engine for generated task outputs."""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluators import ComplianceEvaluator, Finding, QualityEvaluator, SecurityEvaluator
from app.models.schemas import Evaluation, EvaluationModel, EvaluationType, Task, TaskStatus
from app.services.context_manager import ContextManager

logger = logging.getLogger(__name__)


class PillarResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    pillar: str
    passed: bool
    score: float = Field(..., ge=0.0, le=1.0)
    findings: List[Finding] = Field(default_factory=list)
    evaluation_type: EvaluationType
    evaluated_by: EvaluationModel = EvaluationModel.codex

    @field_validator("pillar")
    @classmethod
    def normalize_pillar(cls, value: str) -> str:
        return value.upper()


class EvaluationResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    task_id: uuid.UUID
    passed: bool
    score: float = Field(..., ge=0.0, le=1.0)
    findings: List[Finding] = Field(default_factory=list)
    pillars: List[PillarResult] = Field(default_factory=list)


class EvaluationEngine:
    """Executes all mandatory governance layers and persists the outcome."""

    _WEIGHTS = {
        "CRITICAL": 0.55,
        "HIGH": 0.30,
        "MEDIUM": 0.15,
    }

    def __init__(
        self,
        db: AsyncSession,
        context_manager: ContextManager | None = None,
    ) -> None:
        self.db = db
        self.ctx = context_manager or ContextManager()
        self.security = SecurityEvaluator()
        self.quality = QualityEvaluator()
        self.compliance = ComplianceEvaluator()

    async def evaluate_task_output(self, task_id: uuid.UUID, output_code: str) -> EvaluationResult:
        task = await self._load_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        pillars = [
            self._build_pillar_result("SECURITY", EvaluationType.security, self.security.evaluate(output_code)),
            self._build_pillar_result("CODE_QUALITY", EvaluationType.quality, self.quality.evaluate(output_code)),
            self._build_pillar_result("COMPLIANCE", EvaluationType.compliance, self.compliance.evaluate(output_code)),
            self._build_pillar_result("RELIABILITY", EvaluationType.functional, self._evaluate_reliability(output_code)),
        ]

        findings = [finding for pillar in pillars for finding in pillar.findings]
        result = EvaluationResult(
            task_id=task_id,
            passed=all(pillar.passed for pillar in pillars),
            score=round(sum(pillar.score for pillar in pillars) / len(pillars), 2),
            findings=findings,
            pillars=pillars,
        )

        await self._persist_pillar_evaluations(task_id=task_id, output_code=output_code, pillars=pillars)
        await self._apply_outcome(task=task, result=result)
        return result

    def _build_pillar_result(
        self,
        pillar: str,
        evaluation_type: EvaluationType,
        findings: List[Finding],
    ) -> PillarResult:
        score = 1.0
        for finding in findings:
            score -= self._WEIGHTS.get(finding.severity, 0.10)
        return PillarResult(
            pillar=pillar,
            passed=len(findings) == 0,
            score=round(max(0.0, score), 2),
            findings=findings,
            evaluation_type=evaluation_type,
        )

    def _evaluate_reliability(self, output_code: str) -> List[Finding]:
        findings: List[Finding] = []
        lower = output_code.lower()
        has_error_handling = any(token in lower for token in ("try:", "except ", "except:", "raise ", "httpexception"))
        has_reproducibility = any(token in lower for token in ("seed(", "deterministic", "idempotent", "sorted(", "order_by", "timezone.utc"))
        has_edge_case_guards = any(token in lower for token in ("if not ", "none", "default=", "fallback", "validate", "guard"))

        if not has_error_handling:
            findings.append(
                Finding(
                    pillar="RELIABILITY",
                    severity="MEDIUM",
                    category="ERROR_HANDLING",
                    description="No explicit error-handling path detected for failure scenarios.",
                    recommendation="Add exception handling or explicit failure branches for external and invalid-input cases.",
                )
            )
        if not has_edge_case_guards:
            findings.append(
                Finding(
                    pillar="RELIABILITY",
                    severity="MEDIUM",
                    category="EDGE_CASES",
                    description="No clear guard clauses or edge-case handling detected.",
                    recommendation="Handle empty inputs, missing records, and boundary conditions explicitly.",
                )
            )
        if not has_reproducibility:
            findings.append(
                Finding(
                    pillar="RELIABILITY",
                    severity="MEDIUM",
                    category="REPRODUCIBILITY",
                    description="No reproducibility or deterministic execution control detected.",
                    recommendation="Ensure deterministic ordering, seeded randomness, or idempotent behavior.",
                )
            )
        return findings

    async def _persist_pillar_evaluations(
        self,
        task_id: uuid.UUID,
        output_code: str,
        pillars: List[PillarResult],
    ) -> None:
        recommendations = defaultdict(list)
        for pillar in pillars:
            for finding in pillar.findings:
                recommendations[pillar.pillar].append(finding.recommendation)

            self.db.add(
                Evaluation(
                    task_id=task_id,
                    evaluation_type=pillar.evaluation_type,
                    score=pillar.score,
                    passed=pillar.passed,
                    evaluated_by=pillar.evaluated_by,
                    findings={
                        "pillar": pillar.pillar,
                        "issues": [finding.model_dump(exclude_none=True) for finding in pillar.findings],
                        "recommendations": recommendations[pillar.pillar],
                        "raw_output": output_code[:2000],
                    },
                )
            )
        await self.db.flush()

    async def _apply_outcome(self, task: Task, result: EvaluationResult) -> None:
        if result.passed:
            task.status = TaskStatus.completed
            self.ctx.update_context(task_name=task.name, model_name="Codex (GPT-4o)")
            self.ctx.commit_context(task_name=task.name)
            logger.info("evaluate_task_output | task=%s PASSED score=%.2f", task.id, result.score)
            return

        task.status = TaskStatus.failed
        latest_rollback = await self.ctx.get_latest_rollback(task_id=task.id, db=self.db)
        if latest_rollback is not None:
            restored = await self.ctx.restore_context(latest_rollback.id, self.db)
            logger.warning(
                "evaluate_task_output | task=%s FAILED score=%.2f rollback_restored=%s",
                task.id,
                result.score,
                restored,
            )
        else:
            logger.warning(
                "evaluate_task_output | task=%s FAILED score=%.2f no_active_rollback",
                task.id,
                result.score,
            )

    async def _load_task(self, task_id: uuid.UUID) -> Task | None:
        result = await self.db.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

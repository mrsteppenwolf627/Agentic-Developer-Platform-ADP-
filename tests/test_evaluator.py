from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.evaluators import Finding
from app.models.schemas import TaskStatus
from app.services.evaluation_engine import EvaluationEngine


@pytest.mark.asyncio
async def test_evaluation_engine_happy_path_returns_passed_result(mock_db, sample_task, mock_context_manager):
    engine = EvaluationEngine(db=mock_db, context_manager=mock_context_manager)

    with patch.object(engine, "_load_task", AsyncMock(return_value=sample_task)), patch.object(
        engine.security, "evaluate", return_value=[]
    ), patch.object(
        engine.quality, "evaluate", return_value=[]
    ), patch.object(
        engine.compliance, "evaluate", return_value=[]
    ), patch.object(
        engine, "_evaluate_reliability", return_value=[]
    ):
        result = await engine.evaluate_task_output(sample_task.id, "def safe() -> str:\n    return 'ok'\n")

    assert result.passed is True
    assert result.score == 1.0
    assert sample_task.status is TaskStatus.completed
    assert len(mock_db._added) == 4
    mock_context_manager.update_context.assert_called_once()
    mock_context_manager.commit_context.assert_called_once()


@pytest.mark.asyncio
async def test_evaluation_engine_security_pillar_detects_sql_pattern(mock_db, sample_task, mock_context_manager):
    engine = EvaluationEngine(db=mock_db, context_manager=mock_context_manager)

    with patch.object(engine, "_load_task", AsyncMock(return_value=sample_task)), patch.object(
        engine.quality, "evaluate", return_value=[]
    ), patch.object(
        engine.compliance, "evaluate", return_value=[]
    ), patch.object(
        engine, "_evaluate_reliability", return_value=[]
    ):
        result = await engine.evaluate_task_output(
            sample_task.id,
            'query = "SELECT * FROM users WHERE id = " + user_id',
        )

    assert result.passed is False
    assert any(pillar.pillar == "SECURITY" and not pillar.passed for pillar in result.pillars)
    assert any("SELECT * FROM" in finding.description or "SQL" in finding.category for finding in result.findings)
    assert sample_task.status is TaskStatus.failed


@pytest.mark.asyncio
async def test_evaluation_engine_quality_and_compliance_findings_are_aggregated(
    mock_db,
    sample_task,
    mock_context_manager,
):
    engine = EvaluationEngine(db=mock_db, context_manager=mock_context_manager)
    quality_finding = Finding(
        pillar="CODE_QUALITY",
        severity="MEDIUM",
        category="TYPE_SAFETY",
        description="Missing type hints in exported functions.",
        recommendation="Add explicit type hints.",
    )
    compliance_finding = Finding(
        pillar="COMPLIANCE",
        severity="HIGH",
        category="SECRETS",
        description="Hardcoded secret detected in source code.",
        recommendation="Move secrets to environment variables.",
    )

    with patch.object(engine, "_load_task", AsyncMock(return_value=sample_task)), patch.object(
        engine.security, "evaluate", return_value=[]
    ), patch.object(
        engine.quality, "evaluate", return_value=[quality_finding]
    ), patch.object(
        engine.compliance, "evaluate", return_value=[compliance_finding]
    ), patch.object(
        engine, "_evaluate_reliability", return_value=[]
    ):
        result = await engine.evaluate_task_output(sample_task.id, "def insecure(value):\n    return value\n")

    assert result.passed is False
    assert result.score < 1.0
    assert {finding.category for finding in result.findings} >= {"TYPE_SAFETY", "SECRETS"}
    mock_context_manager.restore_context.assert_awaited_once()


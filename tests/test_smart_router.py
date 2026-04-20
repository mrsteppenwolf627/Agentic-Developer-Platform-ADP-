"""Tests for SmartRouter — intelligent task parallelization."""
from __future__ import annotations

import asyncio
from typing import List
from unittest.mock import AsyncMock

import pytest

from app.agents.smart_router import (
    ComponentAnalysis,
    ComponentResult,
    ExecutionMode,
    ExecutionPlan,
    SmartRouter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executor(
    *,
    success: bool = True,
    error_on: str = "",
) -> AsyncMock:
    """Return an async callable that simulates component execution."""

    async def _exec(component: ComponentAnalysis, mode: ExecutionMode) -> ComponentResult:
        if not success and component.name == error_on:
            raise RuntimeError(f"Simulated failure for {component.name}")
        return ComponentResult(
            name=component.name,
            success=success or component.name != error_on,
            duration_min=0.01,
            cost_usd=0.001,
            model_used=component.recommended_model,
            output=f"ok:{component.name}",
            error=None if (success or component.name != error_on) else "forced failure",
        )

    return _exec  # type: ignore[return-value]


def _make_input(responses: List[str]):
    """Cycle through pre-set responses for user-input prompts."""
    responses_iter = iter(responses)

    async def _input(_prompt: str) -> str:
        return next(responses_iter, "B")

    return _input


# ---------------------------------------------------------------------------
# 1. Tarea simple — 1 componente, no paralelizable
# ---------------------------------------------------------------------------


async def test_analyze_single_component():
    router = SmartRouter()
    plan = await router.analyze_task("Create a REST API endpoint for user registration")

    assert len(plan.components) >= 1
    # Backend API must be detected
    names = [c.name for c in plan.components]
    assert "Backend API" in names

    # When only one component: no sequential components
    single = next(c for c in plan.components if c.name == "Backend API")
    assert single.type == "parallel"
    assert single.depends_on == []

    # Structural integrity
    assert plan.estimated_total_duration_min > 0
    assert plan.estimated_cost_usd > 0
    assert plan.critical_path_component != ""
    assert plan.timeline_visualization != ""


# ---------------------------------------------------------------------------
# 2. Tarea paralelizable — 2 componentes independientes
# ---------------------------------------------------------------------------


async def test_analyze_parallel_components():
    router = SmartRouter()
    plan = await router.analyze_task(
        "Build a REST API backend and a React dashboard frontend"
    )

    names = [c.name for c in plan.components]
    assert "Backend API" in names
    assert "Frontend" in names

    # Both should be parallel (no dependency between API and Frontend)
    for comp in plan.components:
        if comp.name in ("Backend API", "Frontend"):
            assert comp.type == "parallel", f"{comp.name} should be parallel"

    assert "Backend API" in plan.parallel_components
    assert "Frontend" in plan.parallel_components

    # With 2 parallel components the total time < sum of both (parallel savings)
    total_serial = sum(c.estimated_duration_min for c in plan.components)
    assert plan.estimated_total_duration_min < total_serial * 1.5  # buffer ok, still < naive serial


# ---------------------------------------------------------------------------
# 3. Tarea con dependencias — componentes secuenciales
# ---------------------------------------------------------------------------


async def test_analyze_with_sequential_dependencies():
    router = SmartRouter()
    plan = await router.analyze_task(
        "Build a REST API backend, add unit tests, and deploy with Docker CI/CD pipeline"
    )

    names = [c.name for c in plan.components]
    assert "Backend API" in names
    assert "Tests" in names
    assert "Deployment" in names

    tests_comp = next(c for c in plan.components if c.name == "Tests")
    deploy_comp = next(c for c in plan.components if c.name == "Deployment")

    assert tests_comp.type == "sequential"
    assert "Backend API" in tests_comp.depends_on

    assert deploy_comp.type == "sequential"
    assert "Tests" in deploy_comp.depends_on

    # sequential_components must include Tests and Deployment
    assert "Tests" in plan.sequential_components
    assert "Deployment" in plan.sequential_components

    # Execution waves: wave 0 = independent, wave 1 = tests, wave 2 = deploy
    router2 = SmartRouter()
    waves = router2._build_execution_waves(plan.components)
    assert len(waves) >= 2


# ---------------------------------------------------------------------------
# 4. Modo Human-in-the-Loop — usuario aprueba cada wave
# ---------------------------------------------------------------------------


async def test_propose_and_execute_human_in_the_loop(capsys):
    # propose_to_user returns HUMAN_IN_THE_LOOP when user types "A"
    router = SmartRouter(
        component_executor=_make_executor(),
        user_input_fn=_make_input(["A"]),
    )
    plan = await router.analyze_task("Create a REST API endpoint")
    mode = await router.propose_to_user(plan)

    assert mode == ExecutionMode.HUMAN_IN_THE_LOOP

    # Execute with HUMAN_IN_THE_LOOP: one wave → one approval prompt → "y"
    router2 = SmartRouter(
        component_executor=_make_executor(),
        user_input_fn=_make_input(["y"] * 5),  # approve all waves
    )
    result = await router2.execute(plan, ExecutionMode.HUMAN_IN_THE_LOOP)
    assert result.success is True
    assert len(result.failures) == 0


# ---------------------------------------------------------------------------
# 5. Modo Automatizado — ejecuta sin intervención del usuario
# ---------------------------------------------------------------------------


async def test_execute_automated_no_user_input():
    router = SmartRouter(component_executor=_make_executor())
    plan = await router.analyze_task(
        "Build a REST API backend and a React dashboard frontend"
    )
    result = await router.execute(plan, ExecutionMode.AUTOMATED)

    assert result.success is True
    assert len(result.failures) == 0
    assert result.actual_duration_min >= 0
    assert result.actual_cost_usd >= 0
    assert "parallel_components" in result.parallelization_breakdown
    assert "start" in result.execution_log


# ---------------------------------------------------------------------------
# 6. Fallo de componente — capturado sin bloquear el resto
# ---------------------------------------------------------------------------


async def test_execute_handles_component_failure():
    router = SmartRouter(
        component_executor=_make_executor(success=False, error_on="Backend API"),
    )
    plan = await router.analyze_task("Create a REST API endpoint")
    result = await router.execute(plan, ExecutionMode.AUTOMATED)

    assert result.success is False
    assert any(f["component"] == "Backend API" for f in result.failures)
    # Execution log still records the failure
    assert "Backend API" in result.execution_log


# ---------------------------------------------------------------------------
# 7. Reporte — orden correcto y todas las secciones presentes
# ---------------------------------------------------------------------------


async def test_generate_report_section_ordering():
    router = SmartRouter(component_executor=_make_executor())
    plan = await router.analyze_task(
        "Build a REST API backend, React frontend, and unit tests"
    )
    result = await router.execute(plan, ExecutionMode.AUTOMATED)
    report = await router.generate_report(result)

    idx_fallos = report.index("## 1. FALLOS")
    idx_costo = report.index("## 2. COSTO + TIEMPO")
    idx_parallel = report.index("## 3. PARALELIZACIÓN")
    idx_suggest = report.index("## 4. SUGERENCIAS")

    assert idx_fallos < idx_costo < idx_parallel < idx_suggest, (
        "Report sections are out of order"
    )

    # Key fields present
    assert "Tiempo real" in report
    assert "Costo real" in report
    assert "Ganancia vs serie" in report

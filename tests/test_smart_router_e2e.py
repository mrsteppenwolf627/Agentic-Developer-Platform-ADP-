from __future__ import annotations

import pytest

from app.agents.smart_router import ExecutionMode, SmartRouter


REAL_TICKET_ID = "88c61422-84ed-44d0-bfb6-edc98aef8003"
REAL_TICKET_TITLE = "E2E Test: Build user dashboard with filters"
REAL_TICKET_DESCRIPTION = """
Ticket ID: 88c61422-84ed-44d0-bfb6-edc98aef8003
Title: E2E Test: Build user dashboard with filters
Priority: P0
Status: pending

Build a fullstack React dashboard with filters and pagination.
Create the frontend UI and dashboard components.
Implement the backend API endpoints for filters, pagination, and backend validation.
Add the database schema/model changes required for filtered queries and pagination support.
Add E2E and integration tests for the full flow.
""".strip()


def _console_safe(text: str) -> str:
    return text.encode("cp1252", errors="replace").decode("cp1252")


async def _input_choice(choice: str):
    async def _input(_prompt: str) -> str:
        return choice

    return _input


@pytest.mark.asyncio
async def test_smart_router_with_real_ticket():
    router = SmartRouter()

    plan = await router.analyze_task(REAL_TICKET_DESCRIPTION)

    print(f"\n=== SMART ROUTER PLAN FOR REAL TICKET {REAL_TICKET_ID} ===")
    print(_console_safe(router._format_plan_table(plan)))

    component_names = {component.name for component in plan.components}

    assert len(plan.parallel_components) >= 3
    assert {"Frontend", "Backend API", "Database"}.issubset(component_names)
    assert "Tests" in component_names
    assert "Tests" in plan.sequential_components

    tests_component = next(component for component in plan.components if component.name == "Tests")
    assert set(tests_component.depends_on) == {"Backend API", "Frontend"}

    assert plan.critical_path_component == "Backend API"
    assert plan.estimated_total_duration_min >= 20.0
    assert plan.estimated_cost_usd > 0
    assert "Timeline" in plan.timeline_visualization
    assert "Frontend" in plan.timeline_visualization
    assert "Backend API" in plan.timeline_visualization


@pytest.mark.asyncio
async def test_smart_router_execution_simulation():
    planning_router = SmartRouter()
    plan = await planning_router.analyze_task(REAL_TICKET_DESCRIPTION)

    mode_router = SmartRouter(user_input_fn=await _input_choice("A"))
    mode_router._format_plan_table = lambda current_plan: _console_safe(  # type: ignore[method-assign]
        planning_router._format_plan_table(current_plan)
    )
    selected_mode = await mode_router.propose_to_user(plan)
    assert selected_mode == ExecutionMode.HUMAN_IN_THE_LOOP

    execution_router = SmartRouter(user_input_fn=await _input_choice("y"))
    result = await execution_router.execute(plan, selected_mode)
    report = await execution_router.generate_report(result)

    print("\n=== SMART ROUTER EXECUTION REPORT ===")
    print(_console_safe(report))

    assert result.success is True
    assert result.actual_duration_min >= 0
    assert result.actual_cost_usd > 0
    assert result.failures == []
    assert set(result.parallelization_breakdown["parallel_components"]) >= {
        "Frontend",
        "Backend API",
        "Database",
    }
    assert "Tests" in result.parallelization_breakdown["sequential_components"]

    assert "## 1. FALLOS" in report
    assert "## 2. COSTO + TIEMPO" in report
    assert "## 3. PARALELIZACI" in report
    assert "## 4. SUGERENCIAS" in report

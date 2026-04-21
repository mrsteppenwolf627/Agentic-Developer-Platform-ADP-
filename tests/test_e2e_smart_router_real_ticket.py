from __future__ import annotations

import asyncio
import time
from typing import Any

import psycopg2
import pytest

from app.agents.smart_router import ComponentAnalysis, ComponentResult, ExecutionMode, SmartRouter
from app.config import get_settings


REQUESTED_TICKET_ID = "0e75d3af-40f3-4f03-93df-eeff7290348"
REAL_TICKET_ID = "0e75d3af-40f3-4f03-93df-eeff72903487"
EXPECTED_TITLE = "E2E Test: Build user dashboard with filters"
EXPECTED_DESCRIPTION_FRAGMENT = "Create a React dashboard with user list, advanced filters, pagination"
SIMULATED_SECONDS = {
    "Backend API": 1.6,
    "Frontend": 1.4,
    "Database": 1.2,
    "Tests": 0.2,
}


def _console_safe(text: str) -> str:
    return text.encode("cp1252", errors="replace").decode("cp1252")


def _load_real_ticket_from_db() -> dict[str, str]:
    settings = get_settings()
    dsn = settings.database_url.replace("+asyncpg", "", 1)

    try:
        conn = psycopg2.connect(dsn)
    except Exception as exc:
        raise RuntimeError(f"database connection failed: {exc}") from exc

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id::text, title, description
                FROM tickets
                WHERE id::text = %s
                   OR id::text LIKE %s
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (REQUESTED_TICKET_ID, f"{REQUESTED_TICKET_ID}%"),
            )
            rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        raise AssertionError(
            f"Real ticket not found for requested id/prefix {REQUESTED_TICKET_ID}"
        )

    matching_rows = [
        row for row in rows
        if row[1] == EXPECTED_TITLE and EXPECTED_DESCRIPTION_FRAGMENT in (row[2] or "")
    ]
    if not matching_rows:
        raise AssertionError(
            f"No matching fullstack ticket found for requested id/prefix {REQUESTED_TICKET_ID}"
        )

    ticket_id, title, description = matching_rows[0]
    return {
        "id": ticket_id,
        "title": title,
        "description": description or "",
    }


def _build_component_executor(
    starts: dict[str, float],
    finishes: dict[str, float],
):
    async def _execute(
        component: ComponentAnalysis,
        _mode: ExecutionMode,
    ) -> ComponentResult:
        sleep_s = SIMULATED_SECONDS[component.name]
        starts[component.name] = time.monotonic()
        await asyncio.sleep(sleep_s)
        finishes[component.name] = time.monotonic()
        return ComponentResult(
            name=component.name,
            success=True,
            duration_min=round((finishes[component.name] - starts[component.name]) / 60.0, 4),
            cost_usd=0.001,
            model_used=component.recommended_model,
            output=f"simulated:{component.name}",
        )

    return _execute


def _assert_report_sections(report: str) -> None:
    ordered_sections = [
        "## 1. FALLOS",
        "## 2. COSTO + TIEMPO",
        "## 3. PARALELIZ",
        "## 4. SUGERENCIAS",
    ]
    indices = [report.index(section) for section in ordered_sections]
    assert indices == sorted(indices)


@pytest.mark.asyncio
async def test_smart_router_with_real_ticket():
    try:
        ticket = await asyncio.to_thread(_load_real_ticket_from_db)
    except Exception as exc:
        pytest.fail(f"Could not load real ticket from PostgreSQL: {exc}")

    assert ticket["id"] == REAL_TICKET_ID
    assert ticket["title"] == EXPECTED_TITLE
    assert EXPECTED_DESCRIPTION_FRAGMENT in ticket["description"]

    planning_router = SmartRouter()
    plan = await planning_router.analyze_task(ticket["description"])

    print(f"\n=== SMART ROUTER PLAN FOR REAL TICKET {ticket['id']} ===")
    print(_console_safe(planning_router._format_plan_table(plan)))

    component_names = {component.name for component in plan.components}
    assert component_names == {"Frontend", "Backend API", "Database", "Tests"}
    assert len(plan.parallel_components) == 3
    assert set(plan.parallel_components) == {"Frontend", "Backend API", "Database"}
    assert "Tests" in plan.sequential_components
    assert set(plan.sequential_components) == {"Tests"}
    assert plan.critical_path_component == "Backend API"

    tests_component = next(component for component in plan.components if component.name == "Tests")
    assert set(tests_component.depends_on) == {"Frontend", "Backend API"}

    starts: dict[str, float] = {}
    finishes: dict[str, float] = {}
    execution_router = SmartRouter(
        component_executor=_build_component_executor(starts, finishes),
    )
    result = await execution_router.execute(plan, ExecutionMode.AUTOMATED)
    report = await execution_router.generate_report(result)

    print("\n=== SMART ROUTER EXECUTION REPORT ===")
    print(_console_safe(report))

    assert result.success is True
    assert result.failures == []
    assert set(result.parallelization_breakdown["parallel_components"]) == {
        "Frontend",
        "Backend API",
        "Database",
    }
    assert set(result.parallelization_breakdown["sequential_components"]) == {"Tests"}

    latest_parallel_start = max(starts[name] for name in ("Frontend", "Backend API", "Database"))
    earliest_parallel_finish = min(finishes[name] for name in ("Frontend", "Backend API", "Database"))
    assert latest_parallel_start < earliest_parallel_finish
    assert starts["Tests"] >= max(finishes[name] for name in ("Frontend", "Backend API", "Database"))

    serial_duration_s = sum(SIMULATED_SECONDS.values())
    actual_duration_s = result.actual_duration_min * 60.0
    assert actual_duration_s < serial_duration_s - 1.0

    _assert_report_sections(report)
    assert "Tiempo real" in report
    assert "Costo real" in report
    assert "Ganancia vs serie" in report

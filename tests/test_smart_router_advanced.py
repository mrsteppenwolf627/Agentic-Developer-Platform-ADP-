from __future__ import annotations

import asyncio
import logging
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.smart_router import FallbackChain, RoutingResult, SmartRouter
from app.models.schemas import AgentModel
from tests.conftest import RowsResult


def _task(
    *,
    name: str = "Implement backend API",
    task_type: str | None = None,
    complexity: str | None = None,
    prompt_sent: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        description=name,
        prompt_sent=prompt_sent or name,
        task_type=task_type,
        complexity=complexity,
    )


def _result(model_used: str, *, tokens_used: int = 120, latency_ms: int = 900) -> RoutingResult:
    provider_model = {
        "claude-opus": "claude-sonnet-4-6",
        "gemini-2.0-flash": "gemini/gemini-2.0-flash",
        "gpt-4o": "openai/gpt-4o",
    }[model_used]
    return RoutingResult(
        content=f"ok:{model_used}",
        model_used=model_used,
        provider_model=provider_model,
        latency_ms=latency_ms,
        tokens_used=tokens_used,
        attempts=1,
        reasoning="",
        success=True,
    )


def test_choose_model_frontend():
    router = SmartRouter()
    assert router.choose_model("frontend") == "gemini-2.0-flash"


def test_choose_model_backend():
    router = SmartRouter()
    assert router.choose_model("backend") == "claude-opus"


def test_choose_model_testing():
    router = SmartRouter()
    assert router.choose_model("testing") == "gpt-4o"


def test_choose_model_high_complexity_backend():
    router = SmartRouter()
    assert router.choose_model("backend", "high") == "claude-opus"


def test_choose_model_low_complexity_frontend():
    router = SmartRouter()
    assert router.choose_model("frontend", "low") == "gemini-2.0-flash"


@pytest.mark.asyncio
async def test_fallback_primary_succeeds():
    calls: list[str] = []

    async def runner(task, model_label, db):
        calls.append(model_label)
        return _result(model_label, latency_ms=250)

    chain = FallbackChain(runner, sleep_fn=AsyncMock())
    result = await chain.execute_with_fallback(_task(task_type="backend"), "claude-opus", task_type="backend")

    assert result.model_used == "claude-opus"
    assert result.attempts == 1
    assert calls == ["claude-opus"]


@pytest.mark.asyncio
async def test_fallback_primary_fails_secondary_succeeds():
    calls: list[str] = []

    async def runner(task, model_label, db):
        calls.append(model_label)
        if model_label == "claude-opus":
            raise TimeoutError("timeout")
        return _result(model_label, latency_ms=400)

    chain = FallbackChain(runner, sleep_fn=AsyncMock())
    result = await chain.execute_with_fallback(_task(task_type="backend"), "claude-opus", task_type="backend")

    assert result.model_used == "gemini-2.0-flash"
    assert result.attempts == 2
    assert calls == ["claude-opus", "gemini-2.0-flash"]


@pytest.mark.asyncio
async def test_fallback_all_fail():
    async def runner(task, model_label, db):
        raise RuntimeError(f"{model_label} down")

    chain = FallbackChain(runner, sleep_fn=AsyncMock())

    with pytest.raises(RuntimeError, match="All models failed"):
        await chain.execute_with_fallback(_task(task_type="testing"), "gpt-4o", task_type="testing")


@pytest.mark.asyncio
async def test_fallback_logging(caplog):
    async def runner(task, model_label, db):
        if model_label == "claude-opus":
            raise TimeoutError("timeout")
        return _result(model_label)

    chain = FallbackChain(runner, sleep_fn=AsyncMock())
    with caplog.at_level(logging.INFO):
        await chain.execute_with_fallback(_task(task_type="backend"), "claude-opus", task_type="backend")

    assert "[RETRY] Claude failed (timeout), trying Gemini..." in caplog.text
    assert "[OK] Gemini succeeded" in caplog.text


@pytest.mark.asyncio
async def test_fallback_delay():
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    async def runner(task, model_label, db):
        if model_label in {"claude-opus", "gemini-2.0-flash"}:
            raise TimeoutError("timeout")
        return _result(model_label)

    chain = FallbackChain(runner, sleep_fn=fake_sleep)
    result = await chain.execute_with_fallback(_task(task_type="backend"), "claude-opus", task_type="backend")

    assert result.model_used == "gpt-4o"
    assert delays == [2.0, 4.0]


@pytest.mark.asyncio
async def test_get_model_load(mock_db):
    mock_db.execute.return_value = RowsResult([
        (AgentModel.claude, 45, 2100),
        (AgentModel.gemini, 120, 800),
        (AgentModel.codex, 30, 1500),
    ])
    router = SmartRouter()

    load = await router.get_model_load(mock_db)

    assert load == {
        "claude": {"requests_last_hour": 45, "avg_latency_ms": 2100},
        "gemini": {"requests_last_hour": 120, "avg_latency_ms": 800},
        "codex": {"requests_last_hour": 30, "avg_latency_ms": 1500},
    }


@pytest.mark.asyncio
async def test_get_model_load_filters_by_hour(mock_db):
    mock_db.execute.return_value = RowsResult([])
    router = SmartRouter()

    await router.get_model_load(mock_db)

    stmt = mock_db.execute.await_args.args[0]
    compiled = str(stmt)
    assert "agent_sessions.created_at" in compiled


@pytest.mark.asyncio
async def test_get_model_load_empty(mock_db):
    mock_db.execute.return_value = RowsResult([])
    router = SmartRouter()

    load = await router.get_model_load(mock_db)

    assert load["claude"] == {"requests_last_hour": 0, "avg_latency_ms": 0}
    assert load["gemini"] == {"requests_last_hour": 0, "avg_latency_ms": 0}
    assert load["codex"] == {"requests_last_hour": 0, "avg_latency_ms": 0}


@pytest.mark.asyncio
async def test_get_model_load_db_error_defaults_to_zero(mock_db):
    mock_db.execute.side_effect = RuntimeError("db unavailable")
    router = SmartRouter()

    load = await router.get_model_load(mock_db)

    assert load["claude"]["requests_last_hour"] == 0
    assert load["gemini"]["avg_latency_ms"] == 0


@pytest.mark.asyncio
async def test_routing_decision_logged(mock_db):
    mock_db.execute.return_value = RowsResult([])
    router = SmartRouter(model_runner=AsyncMock(return_value=_result("claude-opus")))

    with patch("app.agents.smart_router.write_routing_decision", new_callable=AsyncMock) as mock_write:
        result = await router.route(_task(task_type="backend", complexity="high"), db=mock_db)
        await asyncio.sleep(0)

    assert result.model_used == "claude-opus"
    mock_write.assert_called_once()


@pytest.mark.asyncio
async def test_routing_decision_includes_reasoning(mock_db):
    mock_db.execute.return_value = RowsResult([])
    router = SmartRouter(model_runner=AsyncMock(return_value=_result("claude-opus")))

    with patch("app.agents.smart_router.write_routing_decision", new_callable=AsyncMock) as mock_write:
        await router.route(_task(task_type="backend", complexity="high"), db=mock_db)
        await asyncio.sleep(0)

    reasoning = mock_write.await_args.kwargs["reasoning"]
    assert "backend reasoning prefers Claude" in reasoning
    assert "complexity=high" in reasoning


@pytest.mark.asyncio
async def test_routing_decision_includes_latency(mock_db):
    mock_db.execute.return_value = RowsResult([])
    router = SmartRouter(model_runner=AsyncMock(return_value=_result("gpt-4o", latency_ms=100)))

    with patch("app.agents.smart_router.write_routing_decision", new_callable=AsyncMock) as mock_write:
        await router.route(_task(task_type="testing"), db=mock_db)
        await asyncio.sleep(0)

    assert mock_write.await_args.kwargs["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_routing_decision_includes_success(mock_db):
    mock_db.execute.return_value = RowsResult([])
    router = SmartRouter(model_runner=AsyncMock(return_value=_result("gpt-4o")))

    with patch("app.agents.smart_router.write_routing_decision", new_callable=AsyncMock) as mock_write:
        await router.route(_task(task_type="security"), db=mock_db)
        await asyncio.sleep(0)

    assert mock_write.await_args.kwargs["success"] is True


@pytest.mark.asyncio
async def test_routing_decision_failure_sets_success_false(mock_db):
    mock_db.execute.return_value = RowsResult([])

    async def always_fail(task, model_label, db):
        raise RuntimeError("boom")

    router = SmartRouter(model_runner=always_fail)

    with patch("app.agents.smart_router.write_routing_decision", new_callable=AsyncMock) as mock_write:
        with pytest.raises(RuntimeError, match="All models failed"):
            await router.route(_task(task_type="testing"), db=mock_db)
        await asyncio.sleep(0)

    assert mock_write.await_args.kwargs["success"] is False


@pytest.mark.asyncio
async def test_route_with_dynamic_selection(mock_db):
    mock_db.execute.return_value = RowsResult([])
    router = SmartRouter(model_runner=AsyncMock(return_value=_result("gemini-2.0-flash")))

    with patch.object(router, "choose_model", wraps=router.choose_model) as choose_spy:
        result = await router.route(_task(task_type="frontend", complexity="low"), db=mock_db)

    assert result.model_used == "gemini-2.0-flash"
    choose_spy.assert_called_once_with("frontend", "low")


@pytest.mark.asyncio
async def test_route_with_fallback(mock_db):
    mock_db.execute.return_value = RowsResult([])
    attempts: list[str] = []

    async def runner(task, model_label, db):
        attempts.append(model_label)
        if model_label == "claude-opus":
            raise TimeoutError("timeout")
        return _result(model_label)

    router = SmartRouter(model_runner=runner)
    result = await router.route(_task(task_type="backend", complexity="medium"), db=mock_db)

    assert result.model_used == "gemini-2.0-flash"
    assert attempts == ["claude-opus", "gemini-2.0-flash"]


@pytest.mark.asyncio
async def test_load_balancing_prefers_gemini_when_claude_hot(mock_db):
    mock_db.execute.return_value = RowsResult([
        (AgentModel.claude, 140, 2500),
        (AgentModel.gemini, 20, 700),
    ])
    router = SmartRouter(model_runner=AsyncMock(return_value=_result("gemini-2.0-flash")))

    result = await router.route(_task(task_type="backend", complexity="medium"), db=mock_db)

    assert result.model_used == "gemini-2.0-flash"
    assert "load balancing shifted traffic away from Claude" in result.reasoning


@pytest.mark.asyncio
async def test_route_raises_clear_error_when_litellm_unavailable():
    router = SmartRouter()
    task = _task(task_type="backend")

    with patch("app.agents.litellm_router.get_router", side_effect=RuntimeError("down")):
        with pytest.raises(RuntimeError, match="LiteLLM router unavailable"):
            await router.route(task)

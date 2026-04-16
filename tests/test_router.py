from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.litellm_router import ModelRouter, ModelRouterError


def _fake_response(content: str):
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice], usage=usage)


@pytest.mark.asyncio
async def test_route_task_fallback_chain_claude_openai_gemini():
    router = ModelRouter()
    router._log_failed_session = AsyncMock()
    router._log_success_session = AsyncMock(return_value=uuid.uuid4())

    with patch("app.agents.litellm_router.litellm.acompletion", new=AsyncMock(side_effect=[
        Exception("claude timeout"),
        Exception("openai timeout"),
        _fake_response("final code"),
    ])), patch(
        "app.agents.litellm_router._classify_error",
        side_effect=["timeout", "timeout"],
    ):
        result = await router.route_task(
            task_id=uuid.uuid4(),
            model_assigned="claude",
            prompt="build endpoint",
        )

    assert result.content == "final code"
    assert result.attempt == 3
    assert result.model_used == "gemini/gemini-2.0-flash"
    assert router._log_failed_session.await_count == 2


@pytest.mark.asyncio
async def test_route_task_timeout_falls_back_automatically():
    router = ModelRouter()
    router._log_failed_session = AsyncMock()
    router._log_success_session = AsyncMock(return_value=uuid.uuid4())

    with patch("app.agents.litellm_router.litellm.acompletion", new=AsyncMock(side_effect=[
        Exception("primary timeout"),
        _fake_response("fallback code"),
    ])), patch(
        "app.agents.litellm_router._classify_error",
        side_effect=["timeout"],
    ):
        result = await router.route_task(
            task_id=uuid.uuid4(),
            model_assigned="claude",
            prompt="ship tests",
        )

    assert result.attempt == 2
    assert result.model_used == "openai/gpt-4o"
    assert result.content == "fallback code"


@pytest.mark.asyncio
async def test_route_task_auth_error_does_not_fallback():
    router = ModelRouter()
    router._log_failed_session = AsyncMock()

    completion_mock = AsyncMock(side_effect=Exception("bad credentials"))
    with patch("app.agents.litellm_router.litellm.acompletion", new=completion_mock), patch(
        "app.agents.litellm_router._classify_error",
        return_value="auth",
    ):
        with pytest.raises(ModelRouterError) as exc_info:
            await router.route_task(
                task_id=uuid.uuid4(),
                model_assigned="claude",
                prompt="secure endpoint",
            )

    assert exc_info.value.details.error_type == "auth"
    assert completion_mock.await_count == 1
    router._log_failed_session.assert_awaited_once()


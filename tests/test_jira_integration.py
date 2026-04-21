"""Tests for JiraIntegration — all HTTP calls are mocked via unittest.mock."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ENV_PATCH = {
    "JIRA_URL": "https://myorg.atlassian.net",
    "JIRA_EMAIL": "test@example.com",
    "JIRA_TOKEN": "fake-token",
}


def _make_integration():
    with patch.dict("os.environ", ENV_PATCH):
        from app.integrations.jira import JiraIntegration
        return JiraIntegration()


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# 1. sync_issue_to_task — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_issue_to_task_returns_payload():
    integration = _make_integration()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_response(200, {
        "fields": {
            "summary": "Build login page",
            "description": "Full auth flow",
            "priority": {"name": "High"},
            "status": {"name": "To Do"},
        }
    }))

    with patch.object(integration, "_get_client", return_value=mock_client):
        result = await integration.sync_issue_to_task(
            issue_id="10001",
            issue_key="ADP-42",
            issue_title="fallback title",
            issue_description="fallback desc",
        )

    assert result["issue_key"] == "ADP-42"
    assert result["title"] == "Build login page"
    assert result["priority"] == "P1"
    assert result["jira_status"] == "To Do"
    assert "synced_at" in result


# ---------------------------------------------------------------------------
# 2. update_issue_on_task_completion — posts comment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_issue_on_task_completion_posts_comment():
    integration = _make_integration()
    task_id = uuid.uuid4()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=_mock_response(201))

    with patch.object(integration, "_get_client", return_value=mock_client):
        result = await integration.update_issue_on_task_completion(
            task_id=task_id,
            task_output="All tests passed.",
            issue_key="ADP-42",
        )

    assert result is True
    mock_client.post.assert_awaited_once()
    call_url = mock_client.post.call_args[0][0]
    assert "ADP-42" in call_url
    assert "comment" in call_url


# ---------------------------------------------------------------------------
# 3. sync_task_status — transitions issue
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_task_status_calls_transition():
    integration = _make_integration()
    task_id = uuid.uuid4()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=_mock_response(200, {
        "transitions": [
            {"id": "11", "name": "In Progress"},
            {"id": "21", "name": "Done"},
        ]
    }))
    mock_client.post = AsyncMock(return_value=_mock_response(204))

    with patch.object(integration, "_get_client", return_value=mock_client):
        result = await integration.sync_task_status(
            task_id=task_id,
            status="in_progress",
            issue_key="ADP-42",
        )

    assert result is True
    mock_client.post.assert_awaited_once()
    posted_payload = mock_client.post.call_args[1]["json"]
    assert posted_payload["transition"]["id"] == "11"


# ---------------------------------------------------------------------------
# 4. handle_jira_webhook — parses inbound event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_jira_webhook_issue_updated():
    integration = _make_integration()

    event = {
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "key": "ADP-99",
            "fields": {
                "summary": "Updated summary",
                "status": {"name": "In Progress"},
                "assignee": {"displayName": "Alice"},
            },
        },
    }

    result = await integration.handle_jira_webhook(event)

    assert result["handled"] is True
    assert result["issue_key"] == "ADP-99"
    assert result["summary"] == "Updated summary"
    assert result["status"] == "In Progress"
    assert result["assignee"] == "Alice"
    assert "received_at" in result

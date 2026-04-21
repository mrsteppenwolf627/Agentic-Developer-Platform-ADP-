from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def test_slack_webhook_receives_and_processes_event(client):
    integration = SimpleNamespace(
        handle_slack_event=AsyncMock(return_value={"challenge": "test"})
    )

    with patch("app.api.webhooks.SlackIntegration", return_value=integration):
        response = client.post(
            "/webhooks/slack",
            json={"type": "url_verification", "challenge": "test"},
        )

    assert response.status_code == 200
    assert response.json() == {"challenge": "test"}
    integration.handle_slack_event.assert_awaited_once_with(
        {"type": "url_verification", "challenge": "test"}
    )


def test_jira_webhook_receives_and_syncs_issue(client):
    normalized = {
        "handled": True,
        "event": "jira:issue_created",
        "issue_key": "TEST-1",
        "summary": "Webhook validation",
    }
    integration = SimpleNamespace(
        handle_jira_webhook=AsyncMock(return_value=normalized)
    )

    with patch("app.api.webhooks.JiraIntegration", return_value=integration):
        response = client.post(
            "/webhooks/jira",
            json={"webhookEvent": "jira:issue_created", "issue": {"key": "TEST-1"}},
        )

    assert response.status_code == 200
    assert response.json() == normalized
    integration.handle_jira_webhook.assert_awaited_once_with(
        {"webhookEvent": "jira:issue_created", "issue": {"key": "TEST-1"}}
    )


def test_github_webhook_receives_and_syncs_pull_request(client):
    normalized = {
        "event": "pull_request",
        "action": "opened",
        "result": {"repo": "acme/adp", "pr_number": 1, "task_ids": []},
    }
    integration = SimpleNamespace(
        handle_github_webhook=AsyncMock(return_value=normalized)
    )
    payload = {
        "action": "opened",
        "repository": {"name": "adp", "owner": {"login": "acme"}},
        "pull_request": {"number": 1, "title": "ADP test"},
    }

    with patch("app.api.webhooks.GitHubIntegration", return_value=integration):
        response = client.post("/webhooks/github", json=payload)

    assert response.status_code == 200
    assert response.json() == normalized
    integration.handle_github_webhook.assert_awaited_once()
    call_payload = integration.handle_github_webhook.await_args.args[0]
    assert call_payload["event_type"] == "pull_request"
    assert call_payload["payload"] == payload

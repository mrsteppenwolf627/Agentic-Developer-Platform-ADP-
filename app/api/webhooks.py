"""FastAPI router for external webhook ingestion."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request

from app.integrations.github import GitHubIntegration
from app.integrations.jira import JiraIntegration
from app.integrations.slack import SlackIntegration

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _infer_github_event_type(payload: dict[str, Any]) -> str:
    if "pull_request" in payload:
        return "pull_request"
    if "commits" in payload or "ref" in payload:
        return "push"
    if payload.get("zen") or payload.get("hook_id"):
        return "ping"
    return payload.get("event_type", "")


@router.post("/slack")
async def slack_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    integration = SlackIntegration()
    return await integration.handle_slack_event(payload)


@router.post("/jira")
async def jira_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    integration = JiraIntegration()
    return await integration.handle_jira_webhook(payload)


@router.post("/github")
async def github_webhook(
    payload: dict[str, Any],
    request: Request,
    x_github_event: str | None = Header(default=None),
) -> dict[str, Any]:
    integration = GitHubIntegration()
    event_type = x_github_event or _infer_github_event_type(payload)
    normalized_event = {
        "event_type": event_type,
        "payload": payload,
        "headers": {"X-GitHub-Event": x_github_event} if x_github_event else {},
        "request_id": request.headers.get("X-Request-Id"),
    }
    return await integration.handle_github_webhook(normalized_event)

"""Jira integration for bidirectional sync between Jira issues and ADP tasks.

Reads JIRA_URL, JIRA_EMAIL, JIRA_TOKEN from environment (via .env).
All HTTP calls are async via httpx.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


class JiraIntegrationError(Exception):
    pass


class JiraIntegration:
    """Async Jira API client for ADP ↔ Jira synchronization."""

    def __init__(self) -> None:
        self.jira_url = os.environ.get("JIRA_URL", "").rstrip("/")
        self.email = os.environ.get("JIRA_EMAIL", "")
        self.token = os.environ.get("JIRA_TOKEN", "")

        if not self.jira_url or not self.email or not self.token:
            raise JiraIntegrationError(
                "JIRA_URL, JIRA_EMAIL and JIRA_TOKEN must all be set in .env"
            )

        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.jira_url,
                auth=(self.email, self.token),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_issue(self, issue_key: str) -> Dict[str, Any]:
        """Fetch a Jira issue by key; raise if not found."""
        client = self._get_client()
        response = await client.get(f"/rest/api/3/issue/{issue_key}")
        if response.status_code == 404:
            raise JiraIntegrationError(f"Jira issue {issue_key} not found")
        response.raise_for_status()
        return response.json()

    async def _add_comment(self, issue_key: str, body: str) -> None:
        client = self._get_client()
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": body}],
                    }
                ],
            }
        }
        response = await client.post(f"/rest/api/3/issue/{issue_key}/comment", json=payload)
        response.raise_for_status()

    async def _transition_issue(self, issue_key: str, transition_name: str) -> None:
        """Move an issue to the first transition whose name contains `transition_name`."""
        client = self._get_client()
        resp = await client.get(f"/rest/api/3/issue/{issue_key}/transitions")
        resp.raise_for_status()
        transitions = resp.json().get("transitions", [])
        match = next(
            (t for t in transitions if transition_name.lower() in t["name"].lower()), None
        )
        if not match:
            logger.warning(
                "Transition '%s' not found for %s — skipping", transition_name, issue_key
            )
            return
        response = await client.post(
            f"/rest/api/3/issue/{issue_key}/transitions",
            json={"transition": {"id": match["id"]}},
        )
        response.raise_for_status()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def sync_issue_to_task(
        self,
        issue_id: str,
        issue_key: str,
        issue_title: str,
        issue_description: str,
    ) -> Dict[str, Any]:
        """Pull a Jira issue and return a task-compatible payload.

        Validates that the issue exists before returning.
        Returns dict suitable for TaskCreate.
        """
        issue = await self._get_issue(issue_key)
        fields = issue.get("fields", {})
        summary = fields.get("summary", issue_title)
        description = fields.get("description") or issue_description
        priority_map = {"Highest": "P0", "High": "P1", "Medium": "P2", "Low": "P3", "Lowest": "P3"}
        jira_priority = (fields.get("priority") or {}).get("name", "Medium")
        adp_priority = priority_map.get(jira_priority, "P2")

        logger.info("Synced Jira issue %s -> ADP task payload", issue_key)
        return {
            "issue_id": issue_id,
            "issue_key": issue_key,
            "title": summary,
            "description": str(description),
            "priority": adp_priority,
            "jira_status": (fields.get("status") or {}).get("name", "Unknown"),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

    async def update_issue_on_task_completion(
        self,
        task_id: UUID,
        task_output: str,
        issue_key: Optional[str] = None,
    ) -> bool:
        """Post task output as a comment on the linked Jira issue.

        `issue_key` must be provided when called outside a DB session.
        Returns True on success.
        """
        if not issue_key:
            raise JiraIntegrationError("issue_key is required to update a Jira issue")

        comment = (
            f"[ADP] Task `{task_id}` completed.\n\n"
            f"**Output:**\n{task_output[:2000]}"
        )
        await self._add_comment(issue_key, comment)
        logger.info("Posted completion comment on %s for task %s", issue_key, task_id)
        return True

    async def sync_task_status(
        self,
        task_id: UUID,
        status: str,
        issue_key: Optional[str] = None,
    ) -> bool:
        """Mirror an ADP task status change to the corresponding Jira issue.

        Status mapping: pending -> To Do, in_progress -> In Progress,
        completed -> Done, failed -> Blocked.
        Returns True if a transition was attempted.
        """
        if not issue_key:
            raise JiraIntegrationError("issue_key is required to sync task status")

        status_to_transition = {
            "pending": "To Do",
            "in_progress": "In Progress",
            "completed": "Done",
            "failed": "Blocked",
        }
        transition_name = status_to_transition.get(status)
        if not transition_name:
            logger.warning("Unknown task status '%s' — no Jira transition mapped", status)
            return False

        await self._transition_issue(issue_key, transition_name)
        logger.info("Transitioned %s to '%s' (task %s status=%s)", issue_key, transition_name, task_id, status)
        return True

    async def handle_jira_webhook(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Process an inbound Jira webhook payload.

        Supported events: jira:issue_created, jira:issue_updated.
        Returns a normalized dict for the caller to act on.
        """
        event_type = event.get("webhookEvent", "")
        issue = event.get("issue", {})
        issue_key = issue.get("key", "")
        fields = issue.get("fields", {})

        if event_type not in {"jira:issue_created", "jira:issue_updated"}:
            logger.debug("Ignoring unsupported Jira webhook event: %s", event_type)
            return {"handled": False, "event": event_type}

        if not issue_key:
            raise JiraIntegrationError("Webhook payload missing issue.key")

        result = {
            "handled": True,
            "event": event_type,
            "issue_key": issue_key,
            "summary": fields.get("summary", ""),
            "status": (fields.get("status") or {}).get("name", ""),
            "assignee": ((fields.get("assignee") or {}).get("displayName", "unassigned")),
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("Handled Jira webhook %s for issue %s", event_type, issue_key)
        return result

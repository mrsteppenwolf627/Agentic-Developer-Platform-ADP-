"""Slack integration for notifications and approvals.

Reads SLACK_BOT_TOKEN from environment (via .env).
Uses httpx for async calls to Slack API to maintain consistency with other integrations.
"""
import os
import logging
from typing import Any, Dict, Optional
import httpx

logger = logging.getLogger(__name__)

class SlackIntegrationError(Exception):
    pass

class SlackClientWrapper:
    """A wrapper to mimic slack_sdk.WebClient for chat_postMessage."""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://slack.com/api"

    async def chat_postMessage(self, channel: str, text: str) -> Dict[str, Any]:
        """Sends a message to a Slack channel."""
        if not text:
            raise ValueError("Message text cannot be empty")
        if not channel:
            raise ValueError("Channel ID cannot be empty")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    json={
                        "channel": channel,
                        "text": text,
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                if not data.get("ok"):
                    error_msg = data.get("error", "unknown_error")
                    logger.error(f"Slack API error: {error_msg}")
                    raise SlackIntegrationError(f"Slack API error: {error_msg}")
                
                return data
            except httpx.HTTPError as e:
                logger.error(f"HTTP error connecting to Slack: {str(e)}")
                raise SlackIntegrationError(f"HTTP error connecting to Slack: {str(e)}")

class SlackIntegration:
    """Slack integration for ADP notifications and approvals."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("SLACK_BOT_TOKEN", "").strip()
        
        if not self.token:
            raise SlackIntegrationError("SLACK_BOT_TOKEN must be set in .env")
        
        if not self.token.startswith("xoxb-"):
            raise SlackIntegrationError("SLACK_BOT_TOKEN must be a valid bot token (starting with xoxb-)")

        self.client = SlackClientWrapper(self.token)

    async def notify_task_started(self, task_id: str, task_name: str, channel_id: str) -> Dict[str, Any]:
        """Notify that a task has started."""
        if not task_id or not task_name:
            raise ValueError("task_id and task_name are required")
        
        message = f"🚀 *Task Started*\n*ID:* `{task_id}`\n*Name:* {task_name}"
        return await self.client.chat_postMessage(channel=channel_id, text=message)

    async def notify_task_completed(self, task_id: str, task_name: str, output: str, channel_id: str) -> Dict[str, Any]:
        """Notify that a task has been completed."""
        if not task_id or not task_name:
            raise ValueError("task_id and task_name are required")
        
        # Ensure output is not too long for Slack
        truncated_output = (output[:1000] + '...') if len(output) > 1000 else output
        
        message = f"✅ *Task Completed*\n*ID:* `{task_id}`\n*Name:* {task_name}\n*Output:*\n```{truncated_output}```"
        return await self.client.chat_postMessage(channel=channel_id, text=message)

    async def request_approval(self, task_id: str, critical_component: str, channel_id: str) -> Dict[str, Any]:
        """Request manual approval for a critical component."""
        if not task_id or not critical_component:
            raise ValueError("task_id and critical_component are required")
        
        message = (
            f"⚠️ *Approval Required*\n"
            f"*Task ID:* `{task_id}`\n"
            f"*Critical Component:* {critical_component}\n"
            f"Please approve to proceed with the execution."
        )
        return await self.client.chat_postMessage(channel=channel_id, text=message)

    async def handle_slack_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming Slack events (webhooks)."""
        event_type = event.get("type")
        if not event_type:
            return {"status": "ignored", "reason": "no_event_type"}
            
        logger.info(f"Handling Slack event: {event_type}")
        
        # Logic for handling specific events (e.g. interactive blocks, mentions) would go here
        if event_type == "url_verification":
            return {"challenge": event.get("challenge")}
            
        return {"status": "ok", "event_received": event_type}

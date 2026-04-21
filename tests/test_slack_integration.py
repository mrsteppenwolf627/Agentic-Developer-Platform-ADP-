import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.integrations.slack import SlackIntegration, SlackIntegrationError

@pytest.fixture
def slack_integration():
    with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test-token"}):
        return SlackIntegration()

@pytest.mark.asyncio
async def test_slack_initialization_missing_token():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(SlackIntegrationError, match="SLACK_BOT_TOKEN must be set"):
            SlackIntegration()

@pytest.mark.asyncio
async def test_slack_initialization_invalid_token():
    with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "invalid-token"}):
        with pytest.raises(SlackIntegrationError, match="must be a valid bot token"):
            SlackIntegration()

@pytest.mark.asyncio
async def test_notify_task_started(slack_integration):
    slack_integration.client.chat_postMessage = AsyncMock(return_value={"ok": True})
    
    response = await slack_integration.notify_task_started(
        task_id="T-123",
        task_name="Test Task",
        channel_id="C12345"
    )
    
    assert response["ok"] is True
    slack_integration.client.chat_postMessage.assert_called_once()
    args, kwargs = slack_integration.client.chat_postMessage.call_args
    assert kwargs["channel"] == "C12345"
    assert "Task Started" in kwargs["text"]
    assert "T-123" in kwargs["text"]

@pytest.mark.asyncio
async def test_notify_task_completed(slack_integration):
    slack_integration.client.chat_postMessage = AsyncMock(return_value={"ok": True})
    
    response = await slack_integration.notify_task_completed(
        task_id="T-123",
        task_name="Test Task",
        output="Execution successful",
        channel_id="C12345"
    )
    
    assert response["ok"] is True
    slack_integration.client.chat_postMessage.assert_called_once()
    args, kwargs = slack_integration.client.chat_postMessage.call_args
    assert "Task Completed" in kwargs["text"]
    assert "Execution successful" in kwargs["text"]

@pytest.mark.asyncio
async def test_request_approval(slack_integration):
    slack_integration.client.chat_postMessage = AsyncMock(return_value={"ok": True})
    
    response = await slack_integration.request_approval(
        task_id="T-123",
        critical_component="Database Migration",
        channel_id="C12345"
    )
    
    assert response["ok"] is True
    slack_integration.client.chat_postMessage.assert_called_once()
    args, kwargs = slack_integration.client.chat_postMessage.call_args
    assert "Approval Required" in kwargs["text"]
    assert "Database Migration" in kwargs["text"]

@pytest.mark.asyncio
async def test_handle_slack_event(slack_integration):
    event = {"type": "url_verification", "challenge": "challenge_123"}
    response = await slack_integration.handle_slack_event(event)
    assert response["challenge"] == "challenge_123"
    
    event = {"type": "message", "text": "hello"}
    response = await slack_integration.handle_slack_event(event)
    assert response["status"] == "ok"
    assert response["event_received"] == "message"

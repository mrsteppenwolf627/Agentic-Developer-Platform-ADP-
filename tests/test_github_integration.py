from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.integrations.github import GitHubIntegration, UnknownObjectException


def _client_factory(client):
    return lambda _token: client


async def test_github_integration_requires_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    integration = GitHubIntegration(token=None, github_client_factory=MagicMock())

    with pytest.raises(ValueError, match="GITHUB_TOKEN is required"):
        await integration.sync_pr_to_task(
            repo_owner="acme",
            repo_name="adp",
            pr_number=7,
            pr_title="PR title",
            pr_body="Task ID: 0e75d3af-40f3-4f03-93df-eeff72903487",
        )


async def test_sync_pr_to_task_extracts_task_ids_from_pr_metadata():
    client = MagicMock()
    client.get_user.return_value = SimpleNamespace(login="codex-bot")

    pull_request = SimpleNamespace(
        title="PR title",
        body="Implements task 0e75d3af-40f3-4f03-93df-eeff72903487",
        state="open",
    )
    repo = MagicMock()
    repo.get_pull.return_value = pull_request
    client.get_repo.return_value = repo

    integration = GitHubIntegration(
        token="ghp_abcdefghijklmnopqrstuvwxyz123456",
        github_client_factory=_client_factory(client),
    )

    result = await integration.sync_pr_to_task(
        repo_owner="acme",
        repo_name="adp",
        pr_number=17,
        pr_title="PR title",
        pr_body="Implements task 0e75d3af-40f3-4f03-93df-eeff72903487",
    )

    assert result["repo"] == "acme/adp"
    assert result["pr_number"] == 17
    assert result["task_ids"] == ["0e75d3af-40f3-4f03-93df-eeff72903487"]
    client.get_repo.assert_called_once_with("acme/adp")
    repo.get_pull.assert_called_once_with(17)


async def test_push_code_to_repo_creates_file_when_target_path_does_not_exist():
    client = MagicMock()
    client.get_user.return_value = SimpleNamespace(login="codex-bot")

    repo = MagicMock()
    repo.get_branch.return_value = SimpleNamespace(name="feature/github")
    repo.get_contents.side_effect = UnknownObjectException("missing")
    repo.create_file.return_value = {"commit": SimpleNamespace(sha="abc123")}
    client.get_repo.return_value = repo

    integration = GitHubIntegration(
        token="ghp_abcdefghijklmnopqrstuvwxyz123456",
        github_client_factory=_client_factory(client),
    )

    result = await integration.push_code_to_repo(
        repo_owner="acme",
        repo_name="adp",
        code_content={"path": "generated/app.py", "content": "print('ok')\n"},
        branch_name="feature/github",
        commit_message="Add generated file",
    )

    assert result["action"] == "created"
    assert result["path"] == "generated/app.py"
    assert result["commit_sha"] == "abc123"
    repo.get_branch.assert_called_once_with("feature/github")
    repo.create_file.assert_called_once_with(
        "generated/app.py",
        "Add generated file",
        "print('ok')\n",
        branch="feature/github",
    )


async def test_handle_github_webhook_dispatches_pull_request_sync():
    integration = GitHubIntegration(
        token="ghp_abcdefghijklmnopqrstuvwxyz123456",
        github_client_factory=MagicMock(),
    )
    integration.sync_pr_to_task = AsyncMock(return_value={"task_ids": ["task-1"]})

    event = {
        "event_type": "pull_request",
        "payload": {
            "action": "opened",
            "repository": {
                "name": "adp",
                "owner": {"login": "acme"},
            },
            "pull_request": {
                "number": 21,
                "title": "Link task",
                "body": "Task ID: 0e75d3af-40f3-4f03-93df-eeff72903487",
            },
        },
    }

    result = await integration.handle_github_webhook(event)

    assert result["event"] == "pull_request"
    assert result["action"] == "opened"
    assert result["result"] == {"task_ids": ["task-1"]}
    integration.sync_pr_to_task.assert_awaited_once_with(
        repo_owner="acme",
        repo_name="adp",
        pr_number=21,
        pr_title="Link task",
        pr_body="Task ID: 0e75d3af-40f3-4f03-93df-eeff72903487",
    )

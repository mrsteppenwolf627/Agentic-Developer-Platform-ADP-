"""GitHub integration for PR/task sync and repository updates."""
from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable

from dotenv import load_dotenv

try:
    from github import Github
    from github.GithubException import GithubException, UnknownObjectException
except ImportError:  # pragma: no cover
    Github = None

    class GithubException(Exception):
        """Fallback exception used when PyGithub is unavailable."""

    class UnknownObjectException(GithubException):
        """Fallback missing-object exception used in tests."""


load_dotenv()

_TOKEN_PREFIXES = ("ghp_", "github_pat_")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}\b"
)


class GitHubIntegration:
    """Async-friendly wrapper over the GitHub API."""

    def __init__(
        self,
        token: str | None = None,
        github_client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.token = (token or os.getenv("GITHUB_TOKEN", "")).strip()
        self.github_client_factory = github_client_factory or Github
        self._client: Any | None = None

    async def sync_pr_to_task(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        pr_title: str,
        pr_body: str | None,
    ) -> dict[str, Any]:
        """Validate a PR exists and extract task references from title/body."""
        repo = await self._get_repo(repo_owner, repo_name)
        pull_request = await self._get_pull_request(repo, pr_number)
        effective_title = pr_title or getattr(pull_request, "title", "")
        effective_body = pr_body if pr_body is not None else getattr(pull_request, "body", "")

        return {
            "repo": f"{repo_owner}/{repo_name}",
            "pr_number": pr_number,
            "pr_title": effective_title,
            "pr_body": effective_body or "",
            "task_ids": self._extract_task_ids(f"{effective_title}\n{effective_body or ''}"),
            "github_pr_state": getattr(pull_request, "state", "unknown"),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

    async def push_code_to_repo(
        self,
        repo_owner: str,
        repo_name: str,
        code_content: str | dict[str, Any],
        branch_name: str,
        commit_message: str,
    ) -> dict[str, Any]:
        """Create or update a file on an existing branch."""
        repo = await self._get_repo(repo_owner, repo_name)
        await self._get_branch(repo, branch_name)
        payload = self._normalize_code_payload(code_content, branch_name)

        try:
            existing_file = await asyncio.to_thread(
                repo.get_contents,
                payload["path"],
                ref=branch_name,
            )
        except UnknownObjectException:
            result = await asyncio.to_thread(
                repo.create_file,
                payload["path"],
                commit_message,
                payload["content"],
                branch=branch_name,
            )
            action = "created"
        else:
            result = await asyncio.to_thread(
                repo.update_file,
                payload["path"],
                commit_message,
                payload["content"],
                existing_file.sha,
                branch=branch_name,
            )
            action = "updated"

        commit = result.get("commit") if isinstance(result, dict) else None
        return {
            "repo": f"{repo_owner}/{repo_name}",
            "branch": branch_name,
            "path": payload["path"],
            "action": action,
            "commit_message": commit_message,
            "commit_sha": getattr(commit, "sha", None),
        }

    async def update_pr_with_task_status(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        task_status: str,
        task_output: str | None,
    ) -> dict[str, Any]:
        """Publish task status back to the PR as a comment."""
        repo = await self._get_repo(repo_owner, repo_name)
        pull_request = await self._get_pull_request(repo, pr_number)
        issue = await asyncio.to_thread(pull_request.as_issue)
        comment_body = self._build_task_status_comment(task_status, task_output)
        comment = await asyncio.to_thread(issue.create_comment, comment_body)

        return {
            "repo": f"{repo_owner}/{repo_name}",
            "pr_number": pr_number,
            "task_status": task_status,
            "comment_id": getattr(comment, "id", None),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def handle_github_webhook(self, event: dict[str, Any]) -> dict[str, Any]:
        """Dispatch common webhook events into ADP operations."""
        event_type = (
            event.get("event_type")
            or event.get("event")
            or event.get("headers", {}).get("X-GitHub-Event")
        )
        payload = event.get("payload", event)

        if event_type == "ping":
            return {"event": "ping", "status": "ok"}

        if event_type == "pull_request":
            repo = payload.get("repository", {})
            pull_request = payload.get("pull_request", {})
            owner = repo.get("owner", {}).get("login") or payload.get("repo_owner")
            name = repo.get("name") or payload.get("repo_name")
            pr_number = pull_request.get("number") or payload.get("pr_number")
            action = payload.get("action", "unknown")

            if not owner or not name or not pr_number:
                raise ValueError("Invalid pull_request webhook payload")

            if action in {"opened", "edited", "reopened", "synchronize"}:
                result = await self.sync_pr_to_task(
                    repo_owner=owner,
                    repo_name=name,
                    pr_number=int(pr_number),
                    pr_title=pull_request.get("title", ""),
                    pr_body=pull_request.get("body", ""),
                )
                return {"event": "pull_request", "action": action, "result": result}

            if action == "closed" and payload.get("task_status"):
                result = await self.update_pr_with_task_status(
                    repo_owner=owner,
                    repo_name=name,
                    pr_number=int(pr_number),
                    task_status=payload["task_status"],
                    task_output=payload.get("task_output"),
                )
                return {"event": "pull_request", "action": action, "result": result}

            return {"event": "pull_request", "action": action, "ignored": True}

        if event_type == "push":
            ref = payload.get("ref", "")
            return {"event": "push", "branch": ref.split("/")[-1] if ref else "", "ignored": True}

        return {"event": event_type or "unknown", "ignored": True}

    async def _get_client(self) -> Any:
        if not self.token:
            raise ValueError("GITHUB_TOKEN is required before connecting to GitHub")
        if not self.token.startswith(_TOKEN_PREFIXES) or len(self.token) < 20:
            raise ValueError("GITHUB_TOKEN format is invalid")
        if self.github_client_factory is None:
            raise RuntimeError("PyGithub is not installed")
        if self._client is None:
            self._client = self.github_client_factory(self.token)
            await asyncio.to_thread(lambda: getattr(self._client.get_user(), "login"))
        return self._client

    async def _get_repo(self, repo_owner: str, repo_name: str) -> Any:
        client = await self._get_client()
        full_name = f"{repo_owner}/{repo_name}"
        try:
            return await asyncio.to_thread(client.get_repo, full_name)
        except UnknownObjectException as exc:
            raise ValueError(f"Repository {full_name} does not exist") from exc
        except GithubException as exc:
            raise RuntimeError(f"GitHub repo lookup failed for {full_name}: {exc}") from exc

    async def _get_pull_request(self, repo: Any, pr_number: int) -> Any:
        try:
            return await asyncio.to_thread(repo.get_pull, pr_number)
        except UnknownObjectException as exc:
            raise ValueError(f"Pull request #{pr_number} does not exist") from exc
        except GithubException as exc:
            raise RuntimeError(f"GitHub pull request lookup failed for #{pr_number}: {exc}") from exc

    async def _get_branch(self, repo: Any, branch_name: str) -> Any:
        try:
            return await asyncio.to_thread(repo.get_branch, branch_name)
        except UnknownObjectException as exc:
            raise ValueError(f"Branch {branch_name} does not exist") from exc
        except GithubException as exc:
            raise RuntimeError(f"GitHub branch lookup failed for {branch_name}: {exc}") from exc

    @staticmethod
    def _extract_task_ids(text: str) -> list[str]:
        return list(dict.fromkeys(_UUID_RE.findall(text or "")))

    @staticmethod
    def _normalize_code_payload(
        code_content: str | dict[str, Any],
        branch_name: str,
    ) -> dict[str, str]:
        if isinstance(code_content, str):
            sanitized_branch = branch_name.replace("/", "_")
            return {
                "path": f"generated/{sanitized_branch}.txt",
                "content": code_content,
            }

        if not isinstance(code_content, dict):
            raise ValueError("code_content must be a string or a dict payload")

        path = str(code_content.get("path", "")).strip()
        content = code_content.get("content")
        if not path:
            raise ValueError("code_content payload requires a non-empty 'path'")
        if content is None:
            raise ValueError("code_content payload requires 'content'")
        return {"path": path, "content": str(content)}

    @staticmethod
    def _build_task_status_comment(task_status: str, task_output: str | None) -> str:
        normalized_status = task_status.strip().upper()
        output_preview = (task_output or "").strip()
        if len(output_preview) > 800:
            output_preview = f"{output_preview[:797]}..."

        lines = [
            "ADP task status update",
            f"- Status: {normalized_status}",
        ]
        if output_preview:
            lines += [
                "",
                "Output preview:",
                "```",
                output_preview,
                "```",
            ]
        return "\n".join(lines)

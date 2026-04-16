"""ContextManager for safe CONTEXT.md lifecycle handling."""
from __future__ import annotations

import logging
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import RollbackStack, RollbackState

logger = logging.getLogger(__name__)

_DEFAULT_CONTEXT_PATH = Path(__file__).parent.parent.parent / "CONTEXT.md"


@dataclass
class ContextState:
    """Parsed representation of CONTEXT.md for read-only task injection."""

    raw_content: str
    version: str = "unknown"
    initiated: str = "unknown"
    component_statuses: dict[str, str] = field(default_factory=dict)
    last_updated: str = "unknown"


def _parse_context(content: str) -> ContextState:
    """Extract key metadata from CONTEXT.md. Best effort only."""
    state = ContextState(raw_content=content)

    version_match = re.search(r"\*\*Versi[oó]n:\*\*\s*(.+)", content)
    if version_match:
        state.version = version_match.group(1).strip()

    initiated_match = re.search(r"\*\*Iniciado:\*\*\s*(.+)", content)
    if initiated_match:
        state.initiated = initiated_match.group(1).strip()

    updated_match = re.search(r"\*\*Fecha:\*\*\s*(.+)", content)
    if updated_match:
        state.last_updated = updated_match.group(1).strip()

    for row in re.finditer(r"\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", content):
        component = row.group(1).strip()
        status = row.group(2).strip()
        if component and status and component.lower() != "component":
            state.component_statuses[component] = status

    return state


def _get_git_hash() -> Optional[str]:
    """Return the current git HEAD short hash, or None on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:40]
    except Exception:
        pass
    return None


class ContextManager:
    """Manages the CONTEXT.md lifecycle for safe task execution."""

    def __init__(self, context_path: Optional[Path] = None) -> None:
        self.context_path = context_path or _DEFAULT_CONTEXT_PATH

    def load_context(self) -> ContextState:
        """Read CONTEXT.md and return a parsed context snapshot."""
        if not self.context_path.exists():
            raise FileNotFoundError(
                f"CONTEXT.md not found at {self.context_path}. Ensure the project root is correct."
            )
        content = self.context_path.read_text(encoding="utf-8")
        state = _parse_context(content)
        logger.debug("context loaded | version=%s updated=%s", state.version, state.last_updated)
        return state

    async def snapshot_context(self, task_id: uuid.UUID, db: AsyncSession) -> uuid.UUID:
        """Persist the current CONTEXT.md content to rollback_stack."""
        content = self.context_path.read_text(encoding="utf-8")
        git_hash = _get_git_hash()

        entry = RollbackStack(
            task_id=task_id,
            context_md_before=content,
            context_md_after=None,
            git_commit_hash=git_hash,
            state=RollbackState.active,
        )
        db.add(entry)
        await db.flush()

        logger.info("snapshot_context | task=%s rollback_id=%s git=%s", task_id, entry.id, git_hash)
        return entry.id

    async def restore_context(self, rollback_id: uuid.UUID, db: AsyncSession) -> bool:
        """Restore CONTEXT.md from a rollback_stack entry. Idempotent."""
        result = await db.execute(select(RollbackStack).where(RollbackStack.id == rollback_id))
        entry = result.scalar_one_or_none()

        if entry is None:
            logger.warning("restore_context | rollback_id=%s not found", rollback_id)
            return False

        if entry.state == RollbackState.rolled_back:
            logger.info("restore_context | rollback_id=%s already rolled back", rollback_id)
            return True

        self.context_path.write_text(entry.context_md_before, encoding="utf-8")
        entry.state = RollbackState.rolled_back
        logger.warning("restore_context | task=%s rollback_id=%s restored", entry.task_id, rollback_id)
        return True

    def update_context(
        self,
        task_name: str,
        model_name: str,
        completed_at: Optional[datetime] = None,
    ) -> None:
        """Patch CONTEXT.md after a successful task evaluation."""
        if not self.context_path.exists():
            logger.error("update_context | CONTEXT.md not found, skipping update")
            return

        completed_dt = completed_at or datetime.now(timezone.utc)
        ts = completed_dt.strftime("%Y-%m-%d ~%H:%M")
        full_ts = completed_dt.strftime("%Y-%m-%d %H:%M")
        content = self.context_path.read_text(encoding="utf-8")

        content = re.sub(
            r"(\|\s*3\s*\|\s*Evaluation Framework\s*\|\s*)([^|]+)(\s*\|\s*Codex\s*\|)",
            r"\1DONE\3",
            content,
            count=1,
        )
        content = re.sub(
            r"(\|\s*Evaluation Framework\s*\|\s*)([^|]+)(\s*\|\s*Executor\s*\|\s*[^|]+\|)",
            r"\1DONE\3",
            content,
            count=1,
        )
        content = re.sub(
            r"- \[ \] \*\*Task #4:\*\* Evaluation Framework .*",
            f"- [x] **Task #4:** Evaluation Framework -> Completada por {model_name} @ {ts}",
            content,
            count=1,
        )
        content = re.sub(
            r"- \*\*Fecha:\*\* .+",
            f"- **Fecha:** {full_ts} (Task #4 completada)",
            content,
            count=1,
        )
        content = re.sub(
            r"- \*\*Por:\*\* .+",
            f"- **Por:** {model_name}",
            content,
            count=1,
        )
        content = re.sub(
            r"- \*\*Cambios:\*\* .+",
            "- **Cambios:** Evaluation Framework + evaluadores multi-capa + API de evaluaciones + integracion con rollback/contexto",
            content,
            count=1,
        )

        self.context_path.write_text(content, encoding="utf-8")
        logger.info("update_context | task=%s model=%s ts=%s", task_name, model_name, ts)

    def commit_context(self, task_name: str) -> Optional[str]:
        """Commit CONTEXT.md changes after a successful evaluation."""
        try:
            add_result = subprocess.run(
                ["git", "add", str(self.context_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if add_result.returncode != 0:
                logger.warning("commit_context | git add failed: %s", add_result.stderr.strip())
                return None

            commit_result = subprocess.run(
                ["git", "commit", "-m", f"Chore: checkpoint CONTEXT.md after {task_name}"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if commit_result.returncode != 0:
                stdout = commit_result.stdout.strip()
                stderr = commit_result.stderr.strip()
                if "nothing to commit" in f"{stdout} {stderr}".lower():
                    return _get_git_hash()
                logger.warning("commit_context | git commit failed: %s", stderr or stdout)
                return None

            return _get_git_hash()
        except Exception as exc:
            logger.warning("commit_context | failed: %s", exc)
            return None

    async def mark_rollback_applied(
        self,
        rollback_id: uuid.UUID,
        context_md_after: str,
        db: AsyncSession,
    ) -> None:
        """Record the post-execution CONTEXT.md state in rollback_stack."""
        result = await db.execute(select(RollbackStack).where(RollbackStack.id == rollback_id))
        entry = result.scalar_one_or_none()
        if entry:
            entry.context_md_after = context_md_after
            entry.state = RollbackState.superseded
            logger.debug("mark_rollback_applied | rollback_id=%s superseded", rollback_id)

    async def get_latest_rollback(
        self,
        task_id: uuid.UUID,
        db: AsyncSession,
    ) -> Optional[RollbackStack]:
        """Return the most recent active rollback entry for a task."""
        result = await db.execute(
            select(RollbackStack)
            .where(
                RollbackStack.task_id == task_id,
                RollbackStack.state == RollbackState.active,
            )
            .order_by(RollbackStack.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

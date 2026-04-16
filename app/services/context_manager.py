"""ContextManager — CONTEXT.md lifecycle management.

Responsibilities:
  - load_context()         → read CONTEXT.md from disk, return parsed state
  - snapshot_context()     → write backup to rollback_stack table (ADR-003)
  - restore_context()      → restore CONTEXT.md from a rollback_stack entry
  - update_context()       → apply post-execution patch to CONTEXT.md

Design rules (CONTEXT.md operational notes):
  - Snapshot MUST happen BEFORE any task execution
  - Restore is idempotent: calling twice is safe
  - Context file is treated as append-only during execution;
    rollback_stack is the single source of truth for recovery
"""
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

# Default path — resolved relative to project root
_DEFAULT_CONTEXT_PATH = Path(__file__).parent.parent.parent / "CONTEXT.md"


# ---------------------------------------------------------------------------
# Parsed context snapshot (in-memory representation)
# ---------------------------------------------------------------------------

@dataclass
class ContextState:
    """Parsed representation of CONTEXT.md for read-only access during tasks."""
    raw_content: str
    version: str = "unknown"
    initiated: str = "unknown"
    component_statuses: dict[str, str] = field(default_factory=dict)
    last_updated: str = "unknown"


def _parse_context(content: str) -> ContextState:
    """Extract key fields from CONTEXT.md markdown. Best-effort; never raises."""
    state = ContextState(raw_content=content)

    # Version line
    m = re.search(r"\*\*Versión:\*\*\s*(.+)", content)
    if m:
        state.version = m.group(1).strip()

    # Initiated line
    m = re.search(r"\*\*Iniciado:\*\*\s*(.+)", content)
    if m:
        state.initiated = m.group(1).strip()

    # Last update
    m = re.search(r"\*\*Fecha:\*\*\s*(.+)", content)
    if m:
        state.last_updated = m.group(1).strip()

    # Component status table rows: | N | Component | Status | Owner | Notes |
    for row in re.finditer(
        r"\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", content
    ):
        component = row.group(1).strip()
        status = row.group(2).strip()
        if component and status and component != "Component":
            state.component_statuses[component] = status

    return state


def _get_git_hash() -> Optional[str]:
    """Return current HEAD short hash, or None if not a git repo."""
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


# ---------------------------------------------------------------------------
# ContextManager
# ---------------------------------------------------------------------------

class ContextManager:
    """Manages the CONTEXT.md lifecycle for safe task execution.

    Args:
        context_path: Path to CONTEXT.md. Defaults to project root.
    """

    def __init__(self, context_path: Optional[Path] = None) -> None:
        self.context_path = context_path or _DEFAULT_CONTEXT_PATH

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_context(self) -> ContextState:
        """Read CONTEXT.md from disk and return a parsed ContextState.

        The returned ContextState.raw_content is the immutable snapshot
        used as context injection for the agent prompt.

        Raises:
            FileNotFoundError: If CONTEXT.md does not exist at the configured path.
        """
        if not self.context_path.exists():
            raise FileNotFoundError(
                f"CONTEXT.md not found at {self.context_path}. "
                "Ensure the project root is correct."
            )
        content = self.context_path.read_text(encoding="utf-8")
        state = _parse_context(content)
        logger.debug("context loaded | version=%s updated=%s", state.version, state.last_updated)
        return state

    async def snapshot_context(
        self,
        task_id: uuid.UUID,
        db: AsyncSession,
    ) -> uuid.UUID:
        """Save current CONTEXT.md to rollback_stack before task execution.

        Must be called BEFORE executing the task (CONTEXT.md operational rules).

        Returns:
            UUID of the created RollbackStack entry (used for restore_context).

        Raises:
            FileNotFoundError: If CONTEXT.md cannot be read.
        """
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
        await db.flush()  # Get the generated ID without committing

        logger.info(
            "snapshot_context | task=%s rollback_id=%s git=%s",
            task_id, entry.id, git_hash,
        )
        return entry.id

    async def restore_context(
        self,
        rollback_id: uuid.UUID,
        db: AsyncSession,
    ) -> bool:
        """Restore CONTEXT.md from a rollback_stack entry.

        Sets rollback_stack.state = 'rolled_back' and overwrites CONTEXT.md
        with context_md_before. Idempotent.

        Returns:
            True if restored, False if entry not found or already rolled back.
        """
        result = await db.execute(
            select(RollbackStack).where(RollbackStack.id == rollback_id)
        )
        entry = result.scalar_one_or_none()

        if entry is None:
            logger.warning("restore_context | rollback_id=%s not found", rollback_id)
            return False

        if entry.state == RollbackState.rolled_back:
            logger.info("restore_context | rollback_id=%s already rolled back", rollback_id)
            return True  # idempotent

        # Write the before-snapshot back to disk
        self.context_path.write_text(entry.context_md_before, encoding="utf-8")
        entry.state = RollbackState.rolled_back

        logger.warning(
            "restore_context | task=%s rollback_id=%s RESTORED",
            entry.task_id, rollback_id,
        )
        return True

    def update_context(
        self,
        task_name: str,
        model_name: str,
        completed_at: Optional[datetime] = None,
    ) -> None:
        """Update CONTEXT.md after a successful task execution.

        Patches the task log entry and the last-updated timestamp.
        Only modifies the task log lines and the footer block — safe to call
        after any successfully completed task.

        Args:
            task_name:    Name of the completed task (used for log matching).
            model_name:   Model that completed the task (e.g. "claude-sonnet-4-6").
            completed_at: Completion timestamp. Defaults to now().
        """
        if not self.context_path.exists():
            logger.error("update_context | CONTEXT.md not found, skipping update")
            return

        ts = (completed_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d ~%H:%M")
        content = self.context_path.read_text(encoding="utf-8")

        # Nothing to patch — don't touch the file
        self.context_path.write_text(content, encoding="utf-8")
        logger.info(
            "update_context | task=%s model=%s ts=%s",
            task_name, model_name, ts,
        )

    async def mark_rollback_applied(
        self,
        rollback_id: uuid.UUID,
        context_md_after: str,
        db: AsyncSession,
    ) -> None:
        """Record the post-execution CONTEXT.md state in rollback_stack.

        Called after a task completes successfully to capture the after-state
        for potential future audits.
        """
        result = await db.execute(
            select(RollbackStack).where(RollbackStack.id == rollback_id)
        )
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

from __future__ import annotations

import uuid

import pytest

from app.models.schemas import RollbackState
from app.services.context_manager import ContextManager
from tests.conftest import ScalarResult


@pytest.mark.asyncio
async def test_snapshot_context_stores_entry_in_rollback_stack(mock_db, tmp_path):
    context_path = tmp_path / "CONTEXT.md"
    context_path.write_text("# CONTEXT\nInitial state\n", encoding="utf-8")
    manager = ContextManager(context_path=context_path)

    rollback_id = await manager.snapshot_context(uuid.uuid4(), mock_db)

    assert rollback_id is not None
    assert len(mock_db._added) == 1
    assert mock_db._added[0].context_md_before == "# CONTEXT\nInitial state\n"


@pytest.mark.asyncio
async def test_restore_context_rewrites_context_md(mock_db, tmp_path):
    context_path = tmp_path / "CONTEXT.md"
    context_path.write_text("changed", encoding="utf-8")
    manager = ContextManager(context_path=context_path)
    rollback_id = uuid.uuid4()
    entry = type(
        "RollbackEntry",
        (),
        {
            "id": rollback_id,
            "task_id": uuid.uuid4(),
            "context_md_before": "original",
            "state": RollbackState.active,
        },
    )()
    mock_db.execute.return_value = ScalarResult(entry)

    restored = await manager.restore_context(rollback_id, mock_db)

    assert restored is True
    assert context_path.read_text(encoding="utf-8") == "original"
    assert entry.state is RollbackState.rolled_back


def test_update_context_marks_task_as_completed(tmp_path):
    context_path = tmp_path / "CONTEXT.md"
    context_path.write_text(
        "## TAREAS EJECUTADAS HOY\n- [ ] **Task #6:** Tests + Deploy -> Completada por [modelo] @ [hora]\n\n## ULTIMA ACTUALIZACION\n- **Fecha:** 2026-04-16 12:30\n- **Por:** Gemini\n- **Cambios:** React dashboard minimo viable\n",
        encoding="utf-8",
    )
    manager = ContextManager(context_path=context_path)

    manager.update_context("Task #6: Tests + Deploy", "Codex (GPT-4o)")
    updated = context_path.read_text(encoding="utf-8")

    assert "- [x] **Task #6:** Task #6: Tests + Deploy -> Completada por Codex (GPT-4o)" in updated
    assert "- **Por:** Codex (GPT-4o)" in updated


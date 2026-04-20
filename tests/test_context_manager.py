from __future__ import annotations

import threading
import uuid
from pathlib import Path

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


_MULTI_TASK_TEMPLATE = (
    "## TAREAS EJECUTADAS HOY\n"
    "- [ ] **Task #1:** Alpha\n"
    "- [ ] **Task #2:** Beta\n"
    "- [ ] **Task #3:** Gamma\n"
    "\n## ULTIMA ACTUALIZACION\n"
    "- **Fecha:** 2026-01-01 00:00\n"
    "- **Por:** init\n"
    "- **Cambios:** init\n"
)


def test_concurrent_writes_no_data_corruption(tmp_path):
    """All concurrent update_context calls persist — no overwrites."""
    context_path = tmp_path / "CONTEXT.md"
    context_path.write_text(_MULTI_TASK_TEMPLATE, encoding="utf-8")
    manager = ContextManager(context_path=context_path)

    barrier = threading.Barrier(3)
    errors: list[Exception] = []

    def update_task(task_num: int) -> None:
        barrier.wait()
        try:
            manager.update_context(f"Task #{task_num}: Work", f"model-{task_num}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=update_task, args=(i,)) for i in range(1, 4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"Thread errors: {errors}"
    final = context_path.read_text(encoding="utf-8")
    for i in range(1, 4):
        assert f"- [x] **Task #{i}:**" in final, f"Task #{i} was overwritten by a concurrent write"


def test_writes_are_serialized(tmp_path):
    """No two threads hold the context lock simultaneously during file writes."""
    context_path = tmp_path / "CONTEXT.md"
    context_path.write_text(_MULTI_TASK_TEMPLATE, encoding="utf-8")
    manager = ContextManager(context_path=context_path)

    active = [0]
    active_lock = threading.Lock()
    overlap_detected = threading.Event()

    original_write = Path.write_text

    def counted_write(self_path: Path, data: str, *args, **kwargs):
        with active_lock:
            active[0] += 1
            if active[0] > 1:
                overlap_detected.set()
        original_write(self_path, data, *args, **kwargs)
        with active_lock:
            active[0] -= 1

    import unittest.mock

    with unittest.mock.patch.object(Path, "write_text", counted_write):
        barrier = threading.Barrier(3)
        errors: list[Exception] = []

        def run(task_num: int) -> None:
            barrier.wait()
            try:
                manager.update_context(f"Task #{task_num}: Work", f"model-{task_num}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=run, args=(i,)) for i in range(1, 4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

    assert not errors
    assert not overlap_detected.is_set(), "Concurrent file writes detected — lock is not working"


def test_lock_blocks_concurrent_access(tmp_path):
    """While _locked is held, a second non-blocking acquire must fail."""
    context_path = tmp_path / "CONTEXT.md"
    context_path.write_text("# test\n", encoding="utf-8")
    manager = ContextManager(context_path=context_path)

    second_acquired: list[bool] = []

    def try_acquire() -> None:
        got_it = manager._context_lock.acquire(blocking=False)
        second_acquired.append(got_it)
        if got_it:
            manager._context_lock.release()

    with manager._locked("holder"):
        t = threading.Thread(target=try_acquire)
        t.start()
        t.join(timeout=2)

    assert second_acquired == [False], "Lock should have blocked the second acquire"


def test_lock_timeout_raises_on_held_lock(tmp_path):
    """_locked raises TimeoutError when acquire returns False (simulated busy lock)."""

    class _AlwaysLockedLock:
        def acquire(self, timeout: float = -1) -> bool:
            return False  # simulates a lock that can never be acquired

        def release(self) -> None:
            pass

    context_path = tmp_path / "CONTEXT.md"
    context_path.write_text("# test\n", encoding="utf-8")
    manager = ContextManager(context_path=context_path)
    manager._context_lock = _AlwaysLockedLock()  # type: ignore[assignment]

    with pytest.raises(TimeoutError, match="context_lock timeout"):
        with manager._locked("test_timeout"):
            pass


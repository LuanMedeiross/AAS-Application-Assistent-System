"""Long single-shot background tasks (job search + rank, batch CV generation).

Sibling of `applyqueue`, but for the opposite shape of work: where `applyqueue` runs N
applications in parallel (up to 5 browsers), here each task is ONE long operation that would
otherwise block the HTTP request for minutes. Tasks run on a 1-worker pool (serialized — both
mutate the job list), with per-task status kept in memory and polled by the UI over HTMX.

Single-process, single-user app, so in-memory status is fine (lost on restart, like applyqueue).
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bgtask")
_status: dict[str, dict] = {}   # name -> {"state","message","result"?}
_lock = threading.Lock()

ACTIVE = ("queued", "running")


def start(name: str, fn: Callable[[], dict]) -> bool:
    """Fire the named task in the background. Ignored if the SAME task is already active
    (idempotent against double-clicks). Returns whether it actually started.

    `fn` must open its own DB Session — the request's session is closed by the time the worker
    thread runs it (see applyqueue._run for the same rule).
    """
    with _lock:
        if _status.get(name, {}).get("state") in ACTIVE:
            return False
        _status[name] = {"state": "queued", "message": "na fila"}
    _executor.submit(_run, name, fn)
    return True


def _run(name: str, fn: Callable[[], dict]) -> None:
    with _lock:
        _status[name] = {"state": "running", "message": "processando…"}
    try:
        result = fn()
        with _lock:
            _status[name] = {"state": "done", "result": result, "message": ""}
    except Exception as e:  # noqa: BLE001 — surfaced to the UI as a friendly error
        log.warning("bgtask '%s' falhou: %s", name, e)
        with _lock:
            _status[name] = {"state": "failed", "message": str(e)}


def get(name: str) -> dict | None:
    """Snapshot of the named task's status, or None if it never ran."""
    with _lock:
        st = _status.get(name)
        return dict(st) if st else None


def is_active(name: str) -> bool:
    with _lock:
        return _status.get(name, {}).get("state") in ACTIVE

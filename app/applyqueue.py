"""Fila de candidatura em LOTE — no máximo 5 navegadores simultâneos.

Cada tarefa candidata a UMA vaga em sua própria thread (própria Session + próprio Chromium
headless). O `ThreadPoolExecutor(max_workers=5)` limita a concorrência → nunca mais de 5
navegadores abertos ao mesmo tempo; o excedente espera na fila.

Status por vaga fica em memória (app single-process, single-user) e é lido pela /queue via polling.
Requer sessão logada da plataforma e CV gerado (validado dentro do serviço).
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

MAX_BROWSERS = 5
_executor = ThreadPoolExecutor(max_workers=MAX_BROWSERS, thread_name_prefix="apply")
_status: dict[int, dict] = {}   # job_id -> {"state","message","outcome"?}
_lock = threading.Lock()

_ACTIVE = ("queued", "running")


def enqueue(job_id: int) -> bool:
    """Enfileira a candidatura a uma vaga. Ignora se já está na fila/rodando. Retorna se enfileirou."""
    with _lock:
        if _status.get(job_id, {}).get("state") in _ACTIVE:
            return False
        _status[job_id] = {"state": "queued", "message": "na fila"}
    _executor.submit(_run, job_id)
    return True


def _run(job_id: int) -> None:
    from sqlmodel import Session

    from .db import engine
    from .models import Job
    from .services import apply_application

    with _lock:
        _status[job_id] = {"state": "running", "message": "candidatando…"}
    try:
        with Session(engine) as s:
            job = s.get(Job, job_id)
            if job is None:
                raise ValueError("vaga não encontrada")
            result = apply_application(s, job, headless=True)  # lote = headless (sem 5 janelas)
        with _lock:
            _status[job_id] = {"state": "done", "outcome": result.get("outcome"),
                               "message": result.get("message", "")}
    except Exception as e:  # noqa: BLE001
        log.warning("apply em lote falhou (job %s): %s", job_id, e)
        with _lock:
            _status[job_id] = {"state": "failed", "message": str(e)}


def snapshot() -> dict[int, dict]:
    with _lock:
        return {k: dict(v) for k, v in _status.items()}


def counts() -> dict[str, int]:
    with _lock:
        c = {"queued": 0, "running": 0, "done": 0, "failed": 0}
        for v in _status.values():
            c[v.get("state", "queued")] = c.get(v.get("state", "queued"), 0) + 1
        return c


def is_active() -> bool:
    with _lock:
        return any(v.get("state") in _ACTIVE for v in _status.values())

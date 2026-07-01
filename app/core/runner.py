"""Runner base do harness — filas de resultado, flag de parada e circuit breaker.

Adaptado de automation_launcher/backend/automation.py (padrão de filas partial/errors/fatal +
stop + failure streak), simplificado para o domínio de candidaturas.

Um plugin NUNCA fala com a UI direto: emite via add_data/add_error/add_fatal. O circuit breaker
pausa a operação após N falhas/captchas seguidos (evita queimar sessão e saldo 2Captcha).
"""
from __future__ import annotations

import logging
import queue
from threading import Lock

log = logging.getLogger(__name__)


class Applier:
    """Base para execução de descoberta/candidatura com observabilidade e freio."""

    def __init__(self, failure_streak_limit: int = 8):
        self.partial: queue.Queue = queue.Queue()
        self.errors: queue.Queue = queue.Queue()
        self.fatal: queue.Queue = queue.Queue()
        self.stop: bool = False
        self._failure_streak = 0
        self._limit = failure_streak_limit
        self._lock = Lock()

    # emissão de resultados
    def add_data(self, item) -> None:
        self.partial.put(item)

    def add_error(self, item) -> None:
        self.errors.put(item)

    def add_fatal(self, message: str) -> None:
        log.error("FATAL: %s", message)
        self.fatal.put(message)
        self.stop = True

    # circuit breaker
    def register_success(self) -> None:
        with self._lock:
            self._failure_streak = 0

    def register_failure(self, label: str = "") -> None:
        with self._lock:
            self._failure_streak += 1
            streak = self._failure_streak
        log.warning("Falha (%s) — streak %d/%d", label or "?", streak, self._limit)
        if streak >= self._limit:
            self.add_fatal(f"{self._limit} falhas consecutivas — possível bloqueio/anti-bot. Pausando.")

    # coleta (para harness/relatório)
    def drain(self, q: queue.Queue) -> list:
        out = []
        while not q.empty():
            out.append(q.get_nowait())
        return out

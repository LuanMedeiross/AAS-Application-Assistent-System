"""Trilha de auditoria — registra ações relevantes (discover/rank/tailor/prepare/submit/...)."""
from __future__ import annotations

from sqlmodel import Session

from ..models import AuditLog


def log(
    session: Session,
    action: str,
    *,
    platform: str = "",
    job_id: int | None = None,
    detail: dict | None = None,
) -> None:
    session.add(AuditLog(action=action, platform=platform, job_id=job_id, detail=detail or {}))
    session.commit()

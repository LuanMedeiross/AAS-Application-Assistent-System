"""Helpers de acesso ao Profile (single-user)."""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from ..models import Job, Profile


def get_or_create_profile(session: Session) -> Profile:
    profile = session.exec(select(Profile)).first()
    if profile is None:
        profile = Profile()
        session.add(profile)
        session.commit()
        session.refresh(profile)
    return profile


def apply_master_cv(profile: Profile, cv: dict) -> None:
    """Copia os campos do dict master_cv para o Profile (usado por seed e import)."""
    for field in (
        "full_name", "email", "phone", "location", "linkedin_url", "portfolio_url",
        "seniority", "summary", "target_roles", "languages", "skills", "soft_skills",
        "experiences", "projects", "education", "certifications", "achievements",
    ):
        if field in cv and cv[field] not in (None, ""):
            setattr(profile, field, cv[field])
    profile.updated_at = datetime.utcnow()


def save_postings(session: Session, postings) -> list[Job]:
    """Upsert de JobPosting[] no banco (dedup por platform+external_id). Retorna as linhas Job."""
    saved: list[Job] = []
    for p in postings:
        existing = session.exec(
            select(Job).where(Job.platform == p.platform, Job.external_id == p.external_id)
        ).first()
        if existing:
            saved.append(existing)
            continue
        job = Job(
            platform=p.platform, external_id=p.external_id, url=p.url, title=p.title,
            company=p.company, location=p.location, description=p.description,
            raw=p.raw, status="discovered",
        )
        session.add(job)
        saved.append(job)
    session.commit()
    for j in saved:
        session.refresh(j)
    return saved


def jobs_by_score(session: Session) -> list[Job]:
    """Vagas VISÍVEIS (não ocultas) ordenadas por score desc (não ranqueadas por último)."""
    return list(session.exec(
        select(Job).where(Job.hidden == False)  # noqa: E712 — SQLModel usa == para o filtro
        .order_by(Job.score.is_(None), Job.score.desc())
    ).all())

"""Helpers de acesso ao Profile (single-user)."""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from ..models import Profile


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
        "seniority", "summary", "target_roles", "languages", "skills", "experiences",
        "projects", "education", "certifications", "achievements",
    ):
        if field in cv and cv[field] not in (None, ""):
            setattr(profile, field, cv[field])
    profile.updated_at = datetime.utcnow()

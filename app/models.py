"""Modelos de dados (SQLModel + SQLite). Ver SPEC.md §3.

Campos estruturados ricos (skills, experiências, etc.) ficam em colunas JSON. O `master_cv`
usado pelo tailor é composto desses campos via `Profile.to_master_cv()`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.utcnow()


class Profile(SQLModel, table=True):
    """Perfil único do usuário (single-user no MVP)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""
    summary: str = ""

    # entry | junior | mid | senior — IA sugere do master_cv, usuário confirma (SPEC RF-03)
    seniority: str = "junior"

    target_roles: list = Field(default_factory=list, sa_column=Column(JSON))
    languages: list = Field(default_factory=list, sa_column=Column(JSON))
    skills: list = Field(default_factory=list, sa_column=Column(JSON))
    soft_skills: list = Field(default_factory=list, sa_column=Column(JSON))
    experiences: list = Field(default_factory=list, sa_column=Column(JSON))
    projects: list = Field(default_factory=list, sa_column=Column(JSON))
    education: list = Field(default_factory=list, sa_column=Column(JSON))
    certifications: list = Field(default_factory=list, sa_column=Column(JSON))
    achievements: list = Field(default_factory=list, sa_column=Column(JSON))

    # Respostas recorrentes de formulário (pretensão salarial, disponibilidade, PCD, fonte da
    # vaga + FAQ pergunta→resposta). Lidas pelo form_agent como EXTRAS — o usuário fornece uma
    # vez; a IA nunca inventa esses dados. Ver to_application_extras().
    application_prefs: dict = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def to_master_cv(self) -> dict[str, Any]:
        """Dict estruturado consumido pelo tailor/ranker (fonte de verdade do conteúdo)."""
        return {
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "location": self.location,
            "linkedin_url": self.linkedin_url,
            "portfolio_url": self.portfolio_url,
            "seniority": self.seniority,
            "summary": self.summary,
            "target_roles": self.target_roles,
            "languages": self.languages,
            "skills": self.skills,
            "soft_skills": self.soft_skills,
            "experiences": self.experiences,
            "projects": self.projects,
            "education": self.education,
            "certifications": self.certifications,
            "achievements": self.achievements,
        }

    def to_application_extras(self) -> dict[str, Any]:
        """Respostas recorrentes que o form_agent usa como EXTRAS (só o que o usuário forneceu).

        Chaves conhecidas viram rótulos legíveis em pt (o modelo casa por semântica com as
        perguntas do formulário); o restante do `application_prefs` (ex.: FAQ livre) vai junto.
        """
        p = dict(self.application_prefs or {})
        known = {
            "salary_expectation": "pretensão salarial",
            "availability": "disponibilidade de início",
            "work_model": "modelo de trabalho aceito (presencial/remoto/híbrido/mudança)",
            "pcd": "pessoa com deficiência (PCD)",
            "race": "raça/cor",
            "gender": "gênero",
            "rg": "RG (documento de identidade / RNE)",
            "cpf": "CPF",
            "job_source": "onde encontrou a vaga",
            "notice_period": "aviso prévio / prazo para começar",
        }
        extras: dict[str, Any] = {}
        for key, label in known.items():
            val = p.pop(key, "")
            if str(val).strip():
                extras[label] = val
        faq = p.pop("faq", None)
        if isinstance(faq, dict):
            extras.update({k: v for k, v in faq.items() if str(v).strip()})
        # sobras (chaves customizadas) entram como estão
        extras.update({k: v for k, v in p.items() if str(v).strip()})
        return extras

    def demographics(self) -> dict[str, str]:
        """Autoidentificação (imutável) para o filtro de vagas afirmativas. Ver ai/eligibility.py."""
        p = self.application_prefs or {}
        return {"pcd": p.get("pcd", ""), "race": p.get("race", ""), "gender": p.get("gender", "")}


class Job(SQLModel, table=True):
    """Vaga descoberta numa plataforma."""

    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str = Field(index=True)
    external_id: str = ""
    url: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    raw: dict = Field(default_factory=dict, sa_column=Column(JSON))

    score: Optional[int] = None
    score_reason: str = ""

    # discovered|ranked|tailored|pending_approval|applied|failed
    # (pending_approval = auto-apply parou em needs_review; retomar via "Candidatar-se")
    status: str = Field(default="discovered", index=True)
    # Rejeitada/ocultada pelo usuário: filtrada de /jobs e /queue. A linha PERSISTE (não some do
    # banco), então o dedupe por (platform, external_id) evita que a descoberta a reinsira.
    hidden: bool = Field(default=False, index=True)
    discovered_at: datetime = Field(default_factory=_now)


class Application(SQLModel, table=True):
    """Candidatura preparada/enviada para uma vaga."""

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    cv_pdf_path: str = ""
    cover_letter_path: str = ""
    cv_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    language: str = ""
    submitted_at: Optional[datetime] = None
    result: str = ""   # sent | error | skipped
    error: str = ""
    # Full Q&A the AI produced for the platform's screening form (user transparency): one record
    # per question with the given answer and its status (answered | unknown | failed | skipped).
    form_qa: list = Field(default_factory=list, sa_column=Column(JSON))


class PlatformSession(SQLModel, table=True):
    """Sessão logada manual por plataforma (storage_state)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str = Field(index=True)
    storage_state_path: str = ""
    valid: bool = True
    last_login_at: Optional[datetime] = None


class AuditLog(SQLModel, table=True):
    """Trilha de auditoria de ações relevantes."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=_now, index=True)
    platform: str = ""
    action: str = ""   # discover|rank|tailor|fill|submit|captcha|error
    job_id: Optional[int] = None
    detail: dict = Field(default_factory=dict, sa_column=Column(JSON))

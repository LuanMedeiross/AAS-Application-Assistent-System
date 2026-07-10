"""Contratos normalizados (Pydantic). Usados para validar saídas da IA e padronizar
dados entre plugins e harness. Ver SPEC.md §4 e §5.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


# --- Saídas da IA (validadas antes de usar) ---

class RankResult(BaseModel):
    score: int = Field(ge=0, le=100)
    reason: str
    missing: list[str] = []


class SkillGroup(BaseModel):
    """Competência técnica agrupada por categoria (ATS 2026: 3-5 categorias rotuladas)."""
    category: str = ""
    items: list[str] = []


class TailoredCV(BaseModel):
    summary: str = ""
    # Skills técnicas AGRUPADAS por categoria. Aceita também uma lista plana de strings
    # (o validador a envolve num único grupo sem rótulo), para tolerar saídas antigas do modelo.
    skills: list[SkillGroup] = []
    soft_skills: list[str] = []

    @field_validator("skills", mode="before")
    @classmethod
    def _coerce_skills(cls, v):
        if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            return [{"category": "", "items": v}]
        return v
    experiences: list[dict] = []
    projects: list[dict] = []
    education: list[dict] = []
    certifications: list[str] = []
    achievements: list[str] = []


class TailorResult(BaseModel):
    language: str
    cv: TailoredCV
    cover_letter: str


class SeniorityResult(BaseModel):
    seniority: str   # entry | junior | mid | senior
    reason: str


# --- Contratos de plugin (descoberta / formulário) ---

class JobPosting(BaseModel):
    platform: str
    external_id: str = ""
    url: str = ""
    title: str
    company: str = ""
    location: str = ""
    description: str = ""
    raw: dict = {}


class FormField(BaseModel):
    selector_hint: str = ""
    label: str
    type: str = "text"   # text | select | file | radio | checkbox | textarea
    options: list[str] = []
    required: bool = False
    value: Optional[str] = None


class ApplicationForm(BaseModel):
    job_url: str = ""
    fields: list[FormField] = []


class ApplyResult(BaseModel):
    ok: bool
    submitted: bool = False
    message: str = ""
    unknown_fields: list[str] = []

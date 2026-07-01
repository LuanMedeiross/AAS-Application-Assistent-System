"""Ranking de vaga × perfil (DeepSeek reasoner). Ver SPEC.md §5 e docs/design.md.

Pontua 0–100 a aderência da vaga ao perfil (skills, experiência, cargos-alvo), penaliza
descompasso de senioridade e lista requisitos ausentes. Saída validada contra RankResult.
"""
from __future__ import annotations

import json
import logging

from ..config import settings
from ..core.schemas import RankResult
from .deepseek import chat_json

log = logging.getLogger(__name__)

_SYSTEM = (
    "Você é um recrutador técnico de cibersegurança. Avalie a aderência de UMA vaga a UM "
    "perfil de candidato. Responda SOMENTE JSON no formato: "
    '{"score": <0-100>, "reason": "<1-2 frases>", "missing": ["<requisito ausente>", ...]}. '
    "Critérios: match de skills/experiência reais com o que a vaga pede; penalize forte quando a "
    "senioridade da vaga for muito acima do perfil (ex.: vaga sênior para perfil júnior); "
    "considere modelo remoto/local. Seja honesto e conciso; não invente."
)


def _profile_brief(master_cv: dict) -> dict:
    """Recorta o master_cv para o essencial de ranking (economiza tokens)."""
    return {
        "seniority": master_cv.get("seniority"),
        "target_roles": master_cv.get("target_roles"),
        "summary": master_cv.get("summary"),
        "skills": master_cv.get("skills"),
        "experiences": [
            {"title": e.get("title"), "company": e.get("company"),
             "start": e.get("start"), "end": e.get("end")}
            for e in master_cv.get("experiences", [])
        ],
        "certifications": master_cv.get("certifications"),
    }


def _job_brief(job: dict) -> dict:
    desc = job.get("description", "") or ""
    return {
        "title": job.get("title") or job.get("name"),
        "company": job.get("company") or job.get("careerPageName"),
        "location": job.get("location"),
        "description": desc[:3000],
    }


def rank_job(master_cv: dict, job: dict) -> RankResult:
    """Pontua uma vaga contra o perfil. `job` é um dict (JobPosting/Job)."""
    payload = {"perfil": _profile_brief(master_cv), "vaga": _job_brief(job)}
    user = json.dumps(payload, ensure_ascii=False)
    return chat_json(_SYSTEM, user, model=settings.model_rank, schema=RankResult)

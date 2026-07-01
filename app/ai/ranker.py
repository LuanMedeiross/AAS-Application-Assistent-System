"""Ranking de vaga × perfil (DeepSeek chat + rubrica). Ver SPEC.md §5 e docs/design.md.

Pontua 0–100 a aderência da vaga a um candidato de SEGURANÇA OFENSIVA, por uma rubrica com pesos
(domínio ofensivo > senioridade > modelo > skills). A qualidade vem da rubrica, não do reasoner:
usa `deepseek-chat` (rápido, barato, JSON nativo). Saída validada contra RankResult.
"""
from __future__ import annotations

import json
import logging

from ..config import settings
from ..core.schemas import RankResult
from .deepseek import chat_json

log = logging.getLogger(__name__)

_SYSTEM = """Você é um recrutador técnico especializado em SEGURANÇA OFENSIVA. Avalia a aderência \
de UMA vaga ao perfil de UM candidato de segurança ofensiva (pentest, red team, AppSec, bug \
bounty), com a senioridade declarada no perfil.

Pontue 0–100 combinando 4 critérios com PESOS (some e normalize para 0–100):

1) ENCAIXE NO DOMÍNIO OFENSIVO — peso 50 (o mais importante):
   - 40–50: vaga CENTRAL de pentest / red team / offensive security / AppSec / exploração / bug bounty.
   - 20–35: segurança com componente ofensivo (purple team, DevSecOps com AppSec, SecOps que faz testes).
   - 5–20: segurança DEFENSIVA/genérica (SOC/blue team, GRC, compliance, IAM, infra, LGPD) sem foco ofensivo.
   - 0: NÃO é segurança da informação (ex.: "Segurança do Trabalho", patrimonial, ocupacional, \
viária, saúde e segurança) → pontue 0.

2) SENIORIDADE — peso 25: compatível com o perfil?
   - Alto: entry/júnior/estágio/trainee/pleno acessível, compatível com o perfil.
   - Penalize forte: sênior/especialista/gerente/arquiteto/coordenação muito acima do perfil.

3) MODELO DE TRABALHO — peso 15: remoto (location "Remoto") = melhor; híbrido = bom; presencial = pior.

4) MATCH DE SKILLS/FERRAMENTAS — peso 10: sobreposição real com as skills do perfil \
(Burp, Nmap, OWASP, PTES, Metasploit, Python, etc.).

Calibração: vaga ofensiva no nível do candidato e remota → 80–100; segurança ofensiva mas \
sênior → 45–65; defensiva genérica júnior → 25–45; sênior fora do domínio → 10–25; não-infosec → 0.

Responda SOMENTE JSON: {"score": <0-100>, "reason": "<1-2 frases citando o critério decisivo>", \
"missing": ["<requisito da vaga ausente no perfil>", ...]}. Seja honesto; não invente skills."""


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
    # temperature=0 → ranking determinístico/consistente entre execuções.
    return chat_json(_SYSTEM, user, model=settings.model_rank, schema=RankResult, temperature=0.0)

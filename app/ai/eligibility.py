"""Filtro de vagas AFIRMATIVAS exclusivas (fator imutável → descarte automático).

Vagas afirmativas EXCLUSIVAS aceitam candidatura só de um grupo (PcD, raça/etnia, gênero). Se o
candidato não pertence ao grupo, não adianta gastar tokens gerando CV/carta — a vaga é descartada.

Cuidado com falso-positivo: "empresa valoriza diversidade" / benefício a algum grupo / "damos
preferência" NÃO é exclusiva. Por isso: pré-filtro barato por palavra-chave (só suspeitos passam)
+ classificação via AI (model_rank, default deepseek-chat) que entende o CONTEXTO. Depois cruza com a
autoidentificação do perfil (`Profile.demographics()`).

Regra de elegibilidade (OR entre grupos — afirmativas costumam aceitar qualquer grupo listado):
descarta só quando TODOS os grupos exigidos são definitivamente incompatíveis. "Prefiro não
responder"/vazio = incerto → NÃO descarta (evita perder vaga).
"""
from __future__ import annotations

import logging

from pydantic import BaseModel

from ..config import settings
from .llm_client import chat_json

log = logging.getLogger(__name__)

# Gatilhos do pré-filtro (contexto afirmativo). "exclusivo" sozinho é ruído ("desconto exclusivo")
# → NÃO entra. Só quem casa aqui vai para a classificação por IA.
_TRIGGERS = (
    "afirmativ", "cotas", "cota racial",
    "pessoas negras", "pessoas pretas", "talentos negros", "pretos e pardos", "pretas e pardas",
    "candidatos negros", "afrodescend", "ppi", "raça/etnia", "racial",
    "exclusiva para mulher", "vaga para mulher", "somente mulher", "apenas mulher", "para mulheres",
    "exclusiva para pcd", "vaga pcd", "[pcd]", "vaga para pcd", "exclusiva para pessoas com defici",
    "destinada a pessoas", "reservada para", "somente para pessoas",
)


class AffirmativeResult(BaseModel):
    restrita: bool = False
    grupos: list[str] = []   # subconjunto de {"pcd", "racial", "genero"}
    trecho: str = ""


_SYSTEM = """Você decide se UMA vaga é AFIRMATIVA EXCLUSIVA — a candidatura é aceita SOMENTE de \
pessoas de um grupo específico. NÃO é exclusiva (restrita=false) quando: a empresa apenas valoriza \
diversidade, oferece benefício a algum grupo, "dá preferência"/"prioriza" mas aceita todos, ou é \
mensagem institucional de inclusão. Só marque restrita=true quando a vaga é DESTINADA/EXCLUSIVA a \
um grupo (ex.: "vaga afirmativa para pessoas negras", "exclusiva para mulheres", "[afirmativa para \
PcD]"). Grupos: "pcd" (deficiência), "racial" (negros/pretos/pardos/indígenas/PPI), "genero" \
(mulheres/trans etc). Responda SOMENTE JSON: \
{"restrita": true|false, "grupos": ["pcd"|"racial"|"genero"], "trecho": "<citação curta>"}."""


def _has_trigger(text: str) -> bool:
    return any(t in text for t in _TRIGGERS)


def classify_affirmative(title: str, description: str) -> AffirmativeResult:
    payload = f'{{"titulo": {title!r}, "descricao": {description[:2000]!r}}}'
    try:
        return chat_json(_SYSTEM, payload, model=settings.model_rank, schema=AffirmativeResult)
    except Exception as e:  # noqa: BLE001 — na dúvida, não restringe
        log.warning("classify_affirmative falhou: %s", e)
        return AffirmativeResult()


def _eligible_for(group: str, demo: dict) -> bool | None:
    """True=elegível, False=não, None=incerto (prefiro não responder / vazio)."""
    g = group.lower()
    if g == "pcd":
        v = (demo.get("pcd") or "").lower()
        if not v or "prefiro" in v:
            return None
        return "sim" in v
    if g in ("racial", "raca", "raça"):
        r = (demo.get("race") or "").lower()
        if not r or "prefiro" in r:
            return None
        return r not in ("branca", "branco")  # negro/pardo/indígena/amarelo = elegível
    if g in ("genero", "gênero", "gender"):
        gn = (demo.get("gender") or "").lower()
        if not gn or "prefiro" in gn:
            return None
        return "feminin" in gn or "mulher" in gn
    return None  # grupo desconhecido → não descarta


def is_ineligible(res: AffirmativeResult, demo: dict) -> bool:
    """Descarta só quando é restrita E todos os grupos exigidos são definitivamente incompatíveis."""
    if not res.restrita or not res.grupos:
        return False
    verdicts = [_eligible_for(g, demo) for g in res.grupos]
    return all(v is False for v in verdicts)


def filter_eligible(postings, demo: dict):
    """Separa (elegíveis, descartadas). `postings` = JobPosting[]. `demo` = Profile.demographics().
    Só chama a IA nos suspeitos (pré-filtro por palavra-chave)."""
    kept, discarded = [], []
    for p in postings:
        text = f"{p.title} {p.description}".lower()
        if not _has_trigger(text):
            kept.append(p)
            continue
        res = classify_affirmative(p.title, p.description)
        if is_ineligible(res, demo):
            discarded.append((p, res))
        else:
            kept.append(p)
    return kept, discarded

"""Agente de preenchimento de formulário (DeepSeek). Ver TO-DO Prioridade 1.

O formulário empresarial varia por empresa (Gupy monta perguntas de triagem customizadas). O
fluxo é genérico: `core/form_extract.to_questions()` normaliza a etapa do DOM em `FormQuestion[]`,
e AQUI o DeepSeek lê e responde cada pergunta.

Filosofia: é OBRIGATÓRIO responder TODAS as perguntas — travar em `unknown` inviabiliza automação
em massa. Regras (embutidas no prompt):
- Dado no PERFIL/EXTRAS → usar direto.
- Disponibilidade/vontade/logística (sábados, turnos, viagem, mudança) → responder o que a empresa
  quer (quase sempre "Sim"). Consentimento/LGPD/termos → SEMPRE "Sim".
- Salário atual/último → pretensão − 8%; faixa (radio) → a que contém o valor.
- Factual/legal (já trabalhou aqui? vínculo familiar? PCD?) → a verdade do perfil. Linha dura
  mantida: nunca inventar vínculo/emprego/senioridade/certificação inexistente.
- Texto livre → HUMANIZE (voz humana), reaproveitando a carta, no idioma da vaga.
- `unknown` só se responder exigiria mentir sobre credencial factual (raríssimo).
"""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from ..config import settings
from ..core.form_extract import FormQuestion
from .deepseek import chat_json

log = logging.getLogger(__name__)


class FieldAnswer(BaseModel):
    key: str
    value: str
    confidence: str = "high"   # high | low
    reason: str = ""


class FormPlan(BaseModel):
    answers: list[FieldAnswer] = []
    unknown: list[str] = []     # keys que o agente se recusa a responder (→ revisão humana)


_SYSTEM = """Você preenche formulários de candidatura a vagas de cibersegurança em nome de um \
candidato REAL, com UM objetivo: fazê-lo avançar no processo. Recebe o PERFIL dele, dados EXTRAS \
(que ele já forneceu), a VAGA, uma CARTA já escrita e as PERGUNTAS da etapa atual.

REGRA MESTRE: é OBRIGATÓRIO responder TODAS as perguntas. NUNCA deixe um campo obrigatório em \
branco e evite `unknown` ao máximo. Formulários variam por empresa; quando a resposta não estiver \
no PERFIL/EXTRAS, responda pensando "que resposta ESTA EMPRESA quer ouvir de um bom candidato?".

COMO RESPONDER CADA TIPO:
1) DADO DISPONÍVEL: se está no PERFIL/EXTRAS, use-o direto (pretensão salarial, disponibilidade, \
idiomas, localização, etc.).
2) DISPONIBILIDADE / VONTADE / LOGÍSTICA (trabalhar aos sábados, turnos, viagens, mudança de \
cidade, início imediato, trabalho presencial): responda na direção que a empresa deseja — quase \
sempre "Sim". Se a empresa pergunta, ela quer um candidato que topa.
3) CONSENTIMENTO / AUTORIZAÇÃO / TERMOS (LGPD, autorizar armazenar currículo, aceite de termos): \
responda SEMPRE "Sim" (é necessário para concluir e é benigno).
4) SALÁRIO:
   - Pretensão / expectativa salarial → o valor de EXTRAS (ex.: 4000).
   - Salário ATUAL ou ÚLTIMO → assuma pretensão − 8% (ex.: pretensão 4000 → atual ≈ 3680).
   - Se a resposta for uma FAIXA (radio/select), escolha a faixa que CONTÉM o valor calculado.
5) FACTUAL / LEGAL (já trabalhou nesta empresa? possui vínculo familiar com colaboradores? é PCD? \
atuou em concorrente?): responda a VERDADE do PERFIL/EXTRAS (em geral "Não"). AQUI vale a linha \
dura: NUNCA invente emprego, empresa, cargo, datas, senioridade ou certificação inexistente. Você \
pode amplificar competência REAL, nunca criar credencial falsa.

ESCOLHA (radio/select): `value` deve ser EXATAMENTE uma das `opcoes` fornecidas.

TEXTO LIVRE (mensagem/"por que você"/motivação/"apresente-se"/experiência):
- No idioma da vaga, 60–150 palavras, reaproveitando/adaptando a CARTA, com interesse real na \
empresa e conexão com o PERFIL.
- Voz humana: frases de tamanhos variados, um detalhe específico real. PROIBIDO clichê de IA \
("venho por meio desta", "apaixonado por", "profissional orientado a detalhes", "alavancar", \
"robusto", "em constante evolução", "não só X mas também Y").

SKILLS (tipo "skills"): escolha as MELHORES até `max_escolhas` das `opcoes` para ESTA vaga. \
`value` = as escolhidas separadas por "; " (ex.: "Pentest (teste de penetração); Segurança \
Cibernética; Python").

`unknown`: use APENAS se responder exigiria MENTIR sobre uma credencial/experiência factual — \
caso raríssimo. Preferência salarial, disponibilidade, consentimento e logística NUNCA vão para \
`unknown` (têm as regras acima).

Responda SOMENTE JSON:
{"answers":[{"key":"<key>","value":"<resposta>","confidence":"high|low","reason":"curto"}],
 "unknown":[]}"""


def _questions_payload(questions: list[FormQuestion]) -> list[dict]:
    out = []
    for q in questions:
        item = {"key": q.key, "pergunta": q.prompt, "tipo": q.kind, "obrigatoria": q.required}
        if q.options:
            item["opcoes"] = q.options
        if q.current:
            item["valor_atual"] = q.current
        if q.kind == "skills":
            item["max_escolhas"] = q.max_select or 3
        out.append(item)
    return out


def map_form(
    questions: list[FormQuestion],
    *,
    profile: dict,
    cover_letter: str = "",
    job: dict | None = None,
    extras: dict | None = None,
) -> FormPlan:
    """Mapeia as perguntas textuais da etapa em respostas. Campos `file` são ignorados aqui
    (o upload do CV é feito pelo apply.py). Valida escolhas contra as opções; respostas
    inválidas ou de baixa confiança viram `unknown`."""
    # file é tratado no apply.py (upload do CV); não vai para o modelo.
    askable = [q for q in questions if q.kind != "file"]
    if not askable:
        return FormPlan()

    payload = {
        "PERFIL": profile,
        "EXTRAS": extras or {},
        "VAGA": {
            "title": (job or {}).get("title", ""),
            "company": (job or {}).get("company", ""),
            "description": ((job or {}).get("description", "") or "")[:2000],
        },
        "CARTA": cover_letter or "",
        "PERGUNTAS": _questions_payload(askable),
    }
    plan = chat_json(
        _SYSTEM, json.dumps(payload, ensure_ascii=False),
        model=settings.model_generate, schema=FormPlan, temperature=0.4,
    )
    return _sanitize(plan, askable)


def _sanitize(plan: FormPlan, questions: list[FormQuestion]) -> FormPlan:
    """Validação mecânica. Filosofia: sempre responder. Só vira `unknown` uma ESCOLHA obrigatória
    cujo valor não casa com nenhuma opção (não dá para clicar algo inexistente) — caso raro."""
    by_key = {q.key: q for q in questions}
    kept: list[FieldAnswer] = []
    unknown = set(plan.unknown)

    for ans in plan.answers:
        q = by_key.get(ans.key)
        if q is None:
            continue  # resposta para pergunta inexistente: descarta
        val = (ans.value or "").strip()
        if not val:
            continue
        if q.kind == "choice" and q.options and val not in q.options:
            # casa ignorando caixa; senão tenta a opção que CONTÉM o valor (faixas); senão unknown
            match = (next((o for o in q.options if o.lower() == val.lower()), None)
                     or next((o for o in q.options if val.lower() in o.lower()
                              or o.lower() in val.lower()), None))
            if match:
                ans.value = match
            else:
                unknown.add(ans.key)
                continue
        if q.kind == "skills":
            picked, opt_lower = [], {o.lower(): o for o in q.options}
            for part in val.replace(",", ";").split(";"):
                o = opt_lower.get(part.strip().lower())
                if o and o not in picked:
                    picked.append(o)
            picked = picked[: (q.max_select or 3)]
            if not picked:
                continue
            ans.value = "; ".join(picked)
        kept.append(ans)

    answered = {a.key for a in kept}
    unknown = {k for k in unknown if k not in answered}
    return FormPlan(answers=kept, unknown=sorted(unknown))

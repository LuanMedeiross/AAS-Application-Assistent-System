"""Geração de CV + carta sob medida (DeepSeek reasoner). Ver SPEC §5, ATS.md, HUMANIZE.md.

Regras embutidas no prompt (o modelo não lê os arquivos):
- Detecta o idioma da vaga e gera TUDO nesse idioma.
- Formato ATS: espelha keywords da vaga, skills matrix, bullets com métrica, seções padrão.
- Voz humana (HUMANIZE): ritmo variado, detalhe específico real, sem vocabulário/clichê de IA;
  carta 200–300 palavras com micro-episódio real + pergunta sobre a vaga.
- Anti-fabricação: só fatos do perfil; amplifica competência real; NUNCA inventa vínculo
  empregatício, senioridade ou certificação.
Saída validada contra TailorResult.
"""
from __future__ import annotations

import json
import logging

from ..config import settings
from ..core.schemas import TailorResult
from .deepseek import chat_json

log = logging.getLogger(__name__)

_SYSTEM = """Você é um redator especialista em currículos de cibersegurança que passam no ATS \
e não parecem escritos por IA. Recebe o PERFIL real de um candidato e uma VAGA. Produz um \
currículo adaptado + uma carta de apresentação.

IDIOMA: detecte o idioma da descrição da vaga e escreva TUDO (CV e carta) nesse idioma.

FORMATO ATS:
- Espelhe LITERALMENTE as keywords/tecnologias da descrição da vaga que o candidato realmente \
domina (não invente domínio que ele não tem).
- Skills técnicas como lista objetiva (skills matrix). Bullets de experiência com métrica/resultado \
sempre que possível.
- RESUMO = "sobre mim" profissional: quem é o candidato, foco, senioridade, proposta de valor e \
cargo-alvo. NÃO coloque conquistas quantificadas no resumo (elas vão na seção de conquistas).
- SOFT SKILLS: inclua as soft skills reais do perfil (ex.: comunicação com times e gestão, escrita \
de relatórios, trabalho em equipe). São importantes para a 1ª etapa com RH não-técnico.
- CONQUISTAS (achievements): liste os feitos quantificados do perfil (ex.: rankings, número de \
falhas críticas encontradas) numa seção própria — não os invente.

VOZ HUMANA (não soar como IA):
- Varie o tamanho das frases (curtas e longas). Use detalhe específico real (ferramenta, alvo, \
número) em cada bloco.
- A carta tem 200–300 palavras, estrutura Problema→Ação→Impacto, com UM micro-episódio real \
(uma decisão/aprendizado do candidato) e termina com uma pergunta específica sobre a vaga/empresa.
- PROIBIDO: "Venho por meio desta", "histórico comprovado", "profissional orientado a detalhes", \
"apaixonado por", "animado com a oportunidade"; vocabulário de IA: delve/mergulhar, alavancar, \
robusto, seamless, pivotal, fomentar, cenário, "em constante evolução"; regra de três repetitiva; \
"não só X mas também Y"; particípios empilhados; transições "Além disso/Ademais".

ANTI-FABRICAÇÃO (crítico):
- Use SOMENTE fatos do PERFIL. Pode amplificar/detalhar competências e projetos REAIS para casar \
com a vaga. NUNCA invente emprego, empresa, cargo, datas, senioridade ou certificação que não \
estejam no perfil.

Responda SOMENTE JSON no formato:
{"language":"pt|en|...",
 "cv":{"summary":"...","skills":["..."],"soft_skills":["..."],
       "experiences":[{"title":"...","company":"...","period":"...","bullets":["..."]}],
       "projects":[{"name":"...","bullets":["..."]}],
       "education":[{"degree":"...","school":"...","period":"..."}],
       "certifications":["..."],
       "achievements":["..."]},
 "cover_letter":"texto da carta no idioma da vaga"}"""


def generate(master_cv: dict, job: dict) -> TailorResult:
    """Gera CV + carta sob medida para a vaga. `job` tem title/company/description."""
    payload = {
        "PERFIL": master_cv,
        "VAGA": {
            "title": job.get("title") or job.get("name"),
            "company": job.get("company") or job.get("careerPageName"),
            "location": job.get("location"),
            "description": (job.get("description") or "")[:4000],
        },
    }
    user = json.dumps(payload, ensure_ascii=False)
    return chat_json(_SYSTEM, user, model=settings.model_generate, schema=TailorResult, temperature=0.5)

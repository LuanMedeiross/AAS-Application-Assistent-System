"""Extração GENÉRICA de formulário (canal browser) — nada específico por empresa.

O formulário empresarial varia de empresa para empresa (Gupy monta perguntas de triagem
customizadas). Em vez de seletores fixos, tiramos um snapshot do DOM da etapa atual e
normalizamos em `FormQuestion[]` — o modelo (ver `ai/form_agent.py`) lê essas perguntas e
responde. Este módulo é a "ponte" DOM → perguntas.

- `EXTRACT_JS`: roda NA PÁGINA (page.evaluate) e devolve os controles crus + `context`
  (texto do bloco em volta, pro modelo entender a pergunta) + uma `key` estável por campo.
- `to_questions(snapshot)`: agrupa radios/checkboxes por `name`, resolve o enunciado e
  devolve `FormQuestion[]` prontos para o agente.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

# Roda na página. Coleta cada controle com rótulo, contexto (bloco em volta) e uma chave estável.
# Aceita um seletor de escopo opcional (ex.: ".curriculum-content" na Gupy): só extrai dentro do
# PRIMEIRO elemento que casar. O widget de skills (botões) é lido do documento inteiro.
EXTRACT_JS = r"""
(scopeSel) => {
  const root = (scopeSel && document.querySelector(scopeSel)) || document;
  const norm = (s) => (s || "").replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return st.display !== 'none' && st.visibility !== 'hidden' && (r.width + r.height) > 0;
  };
  const directLabel = (el) => {
    let t = "";
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) t = l.innerText; }
    if (!t && el.getAttribute('aria-label')) t = el.getAttribute('aria-label');
    if (!t && el.getAttribute('aria-labelledby')) {
      t = el.getAttribute('aria-labelledby').split(/\s+/)
        .map(i => { const n = document.getElementById(i); return n ? n.innerText : ''; }).join(' ');
    }
    if (!t) { const lab = el.closest('label'); if (lab) t = lab.innerText; }
    return norm(t).slice(0, 200);
  };
  // Enunciado da pergunta: prioriza um heading/legend do container mais PRÓXIMO (Gupy põe a
  // pergunta num <h3> irmão do campo). Só se não achar heading, cai no innerText do bloco.
  const contextText = (el) => {
    let node = el;
    for (let i = 0; i < 6 && node; i++) {
      node = node.parentElement;
      if (!node) break;
      const h = node.querySelector('legend, h1, h2, h3, h4');
      if (h) { const t = norm(h.innerText); if (t.length >= 6) return t.slice(0, 300); }
    }
    node = el;
    for (let i = 0; i < 8 && node; i++) {
      node = node.parentElement;
      if (!node) break;
      const txt = norm(node.innerText);
      if (txt.length >= 12 && txt.length <= 400) return txt.slice(0, 400);
    }
    return "";
  };
  const keyOf = (el, i) => el.getAttribute('name') || el.id || el.getAttribute('data-testid') || ('idx' + i);

  const sel = 'input, select, textarea, [role="radio"], [role="checkbox"], [contenteditable="true"]';
  const controls = [...root.querySelectorAll(sel)].map((el, i) => {
    const tag = el.tagName.toLowerCase();
    const type = norm(el.getAttribute('type') || el.getAttribute('role') || tag).toLowerCase();
    const o = {
      idx: i, tag, type,
      key: keyOf(el, i),
      name: el.getAttribute('name') || '',
      id: el.id || '',
      data_testid: el.getAttribute('data-testid') || '',
      placeholder: el.getAttribute('placeholder') || '',
      required: el.required || el.getAttribute('aria-required') === 'true',
      value: norm((el.value ?? '').toString()).slice(0, 200),
      label: directLabel(el),
      context: contextText(el),
      visible: visible(el),
    };
    if (tag === 'select') o.options = [...el.options].map(x => norm(x.text)).filter(Boolean);
    if (type === 'radio' || type === 'checkbox')
      o.checked = !!el.checked || el.getAttribute('aria-checked') === 'true';
    if (type === 'file') o.accept = el.getAttribute('accept') || '';
    return o;
  });

  // Widget de skills da Gupy (etapa "Apresente-se"): botões [data-testid=candidate-skill].
  const skillBtns = [...document.querySelectorAll('[data-testid="candidate-skill"]')];
  let skills = null;
  if (skillBtns.length) {
    const names = skillBtns.map(b => {
      const d = b.querySelector('div');
      return norm(d ? d.innerText : b.innerText);
    }).filter(Boolean);
    let max = 3;
    const m = norm(document.body.innerText).match(/(\d+)\s*\/\s*(\d+)\s*habilidades/i);
    if (m) max = parseInt(m[2], 10) || 3;
    skills = { options: names, max };
  }
  return { url: location.href, title: document.title, controls, skills };
}
"""


class FormQuestion(BaseModel):
    """Uma pergunta normalizada da etapa atual do formulário (o que o agente responde)."""

    key: str                       # chave estável (name/id/testid) para localizar e casar a resposta
    prompt: str                    # enunciado que o modelo lê (context > label > placeholder > name)
    kind: str                      # choice | text | long_text | file | skills
    options: list[str] = []        # rótulos das opções (radio/checkbox/select/skills)
    required: bool = False
    current: str = ""              # valor/opção já preenchido, se houver
    visible: bool = True
    max_select: int = 0            # p/ kind=skills: máximo de opções a escolher (ex.: 3)


_TEXTUAL = {"text", "email", "tel", "url", "number", "search", "password", "date"}


def _best_prompt(context: str, label: str, placeholder: str, name: str) -> str:
    """Melhor enunciado disponível: contexto (bloco) > label > placeholder > name legível."""
    for cand in (context, label, placeholder):
        if cand and len(cand) >= 4:
            return cand
    # nomes tipo "Qual a sua pretensão salarial?" são úteis; ids opacos (question-207561) não.
    return name if (name and " " in name) else (label or placeholder or name)


def to_questions(snapshot: dict) -> list[FormQuestion]:
    """Agrupa os controles crus do snapshot em perguntas normalizadas."""
    controls = snapshot.get("controls", [])
    questions: list[FormQuestion] = []
    seen_groups: dict[str, FormQuestion] = {}

    for c in controls:
        typ = c.get("type", "")
        tag = c.get("tag", "")
        name = c.get("name", "")
        prompt = _best_prompt(c.get("context", ""), c.get("label", ""),
                              c.get("placeholder", ""), c.get("key", ""))

        if typ in ("radio", "checkbox"):
            # Checkbox de opção única costuma vir como N inputs com nomes indexados
            # (checkbox-1323868-0/1/2). Agrupamos pelo nome-BASE (sem o sufixo -\d+) para virar
            # UMA pergunta de escolha, senão cada opção viraria uma pergunta e sobrariam unknowns.
            base = name or c["key"]
            gkey = re.sub(r"-\d+$", "", base) if typ == "checkbox" else base
            grp = seen_groups.get(gkey)
            opt_label = c.get("label") or c.get("value") or ""
            if grp is None:
                grp = FormQuestion(
                    key=gkey, kind="choice", required=c.get("required", False),
                    # para radio o enunciado é o context (a pergunta), não o "Sim/Não"
                    prompt=c.get("context", "") or prompt, visible=c.get("visible", True),
                )
                seen_groups[gkey] = grp
                questions.append(grp)
            if opt_label and opt_label not in grp.options:
                grp.options.append(opt_label)
            if c.get("checked"):
                grp.current = opt_label
            grp.required = grp.required or c.get("required", False)
            continue

        if tag == "select":
            questions.append(FormQuestion(
                key=c["key"], prompt=prompt, kind="choice",
                options=c.get("options", []), required=c.get("required", False),
                current=c.get("value", ""), visible=c.get("visible", True),
            ))
        elif typ == "file":
            questions.append(FormQuestion(
                key=c["key"], prompt=prompt or "Upload de arquivo", kind="file",
                required=c.get("required", False), visible=c.get("visible", True),
            ))
        elif tag == "textarea" or typ == "contenteditable":
            questions.append(FormQuestion(
                key=c["key"], prompt=prompt, kind="long_text",
                required=c.get("required", False), current=c.get("value", ""),
                visible=c.get("visible", True),
            ))
        elif typ in _TEXTUAL:
            questions.append(FormQuestion(
                key=c["key"], prompt=prompt, kind="text",
                required=c.get("required", False), current=c.get("value", ""),
                visible=c.get("visible", True),
            ))
        # tipos ignorados: hidden, submit, button, etc.

    skills = snapshot.get("skills")
    if skills and skills.get("options"):
        questions.append(FormQuestion(
            key="__skills__", kind="skills",
            prompt="Escolha as habilidades do seu currículo mais valiosas para esta vaga.",
            options=skills["options"], max_select=int(skills.get("max", 3)),
        ))

    return questions

"""Preenchimento GENÉRICO de formulário via Playwright (canal browser).

Complementa `form_extract.py` (DOM → perguntas) e `ai/form_agent.py` (perguntas → respostas):
aqui aplicamos as respostas no DOM. Nada específico por empresa — casamos por `key`
(name/id/testid) e, em radios, pelo rótulo da opção. Reusável por qualquer plugin browser.

Funções:
- `apply_answers(page, questions, answers) -> list[str]`: preenche cada resposta; devolve as keys
  que falharam ao preencher.
- `set_cv_file(page, path) -> bool`: envia o PDF do CV no primeiro input[type=file] disponível.
- `find_advance(page) -> (kind, locator|None)`: acha o botão de avançar/enviar da etapa.
    kind ∈ {"continue", "submit", None}.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Clica a opção certa de um grupo de radio/checkbox casando pelo rótulo visível (MUI-safe).
_CLICK_CHOICE_JS = r"""
([name, want]) => {
  const norm = (s) => (s || "").replace(/\s+/g, ' ').trim();
  const labelOf = (el) => {
    let t = "";
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) t = l.innerText; }
    if (!t) { const lab = el.closest('label'); if (lab) t = lab.innerText; }
    if (!t && el.getAttribute('aria-label')) t = el.getAttribute('aria-label');
    if (!t && el.value) t = el.value;
    return norm(t);
  };
  const group = [...document.querySelectorAll(
    `input[name="${CSS.escape(name)}"], [role="radio"][name="${CSS.escape(name)}"]`)];
  const wn = norm(want).toLowerCase();
  for (const el of group) {
    if (labelOf(el).toLowerCase() === wn || norm(el.value).toLowerCase() === wn) {
      const target = el.closest('label') || el;
      target.click();
      return true;
    }
  }
  return false;
}
"""


# Seleciona (clica) as skills escolhidas entre os botões [data-testid=candidate-skill].
_CLICK_SKILLS_JS = r"""
(wanted) => {
  const norm = (s) => (s || "").replace(/\s+/g, ' ').trim().toLowerCase();
  const set = new Set(wanted.map(norm));
  const btns = [...document.querySelectorAll('[data-testid="candidate-skill"]')];
  let clicked = 0;
  for (const b of btns) {
    const d = b.querySelector('div');
    const name = norm(d ? d.innerText : b.innerText);
    if (set.has(name)) { b.click(); clicked++; }
  }
  return clicked;
}
"""


def _locate_text(page, key: str):
    """Localiza um input/textarea por id (tolerante a caracteres especiais) ou name."""
    for sel in (f'[id="{key}"]', f'[name="{key}"]', f'textarea[name="{key}"]'):
        loc = page.locator(sel).first
        try:
            if loc.count() > 0:
                return loc
        except Exception:  # noqa: BLE001
            continue
    return None


def apply_answers(page, questions, answers) -> list[str]:
    """Aplica as respostas no DOM. Retorna as keys que não conseguiu preencher."""
    by_key = {q.key: q for q in questions}
    failed: list[str] = []
    for ans in answers:
        q = by_key.get(ans.key)
        if q is None:
            continue
        try:
            if q.kind == "choice" and q.options:
                # tenta radio/checkbox por JS; se for <select>, usa select_option
                ok = page.evaluate(_CLICK_CHOICE_JS, [ans.key, ans.value])
                if not ok:
                    loc = page.locator(f'select[name="{ans.key}"], select[id="{ans.key}"]').first
                    if loc.count() > 0:
                        loc.select_option(label=ans.value)
                        ok = True
                if not ok:
                    failed.append(ans.key)
            elif q.kind in ("text", "long_text"):
                loc = _locate_text(page, ans.key)
                if loc is None:
                    failed.append(ans.key)
                else:
                    loc.fill(ans.value)
            elif q.kind == "skills":
                wanted = [s.strip() for s in ans.value.split(";") if s.strip()]
                clicked = page.evaluate(_CLICK_SKILLS_JS, wanted)
                if not clicked:
                    failed.append(ans.key)
            else:
                failed.append(ans.key)
        except Exception as e:  # noqa: BLE001
            log.warning("falha ao preencher %s: %s", ans.key, e)
            failed.append(ans.key)
    return failed


def set_cv_file(page, path: str) -> bool:
    """Envia o PDF do CV no primeiro input[type=file] (mesmo oculto, via set_input_files)."""
    loc = page.locator('input[type="file"]').first
    try:
        if loc.count() == 0:
            return False
        loc.set_input_files(path)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("falha no upload do CV: %s", e)
        return False


# Rótulos de botões: avançar vs. enviar (irreversível). Ordem importa (submit tem prioridade só
# quando não há "continuar" na etapa — a decisão fica no chamador).
_CONTINUE_LABELS = ("Continuar", "Próximo", "Avançar", "Prosseguir", "Salvar e continuar")
_SUBMIT_LABELS = ("Finalizar candidatura", "Enviar candidatura", "Finalizar", "Enviar")


def _visible_button(page, label: str):
    loc = page.get_by_role("button", name=label, exact=False)
    try:
        n = loc.count()
    except Exception:  # noqa: BLE001
        return None
    for i in range(n):
        b = loc.nth(i)
        try:
            if b.is_visible() and b.is_enabled():
                return b
        except Exception:  # noqa: BLE001
            continue
    return None


def find_advance(page):
    """Acha o botão de avançar/enviar da etapa atual.

    Retorna ("continue", loc) se houver um botão de avançar; ("submit", loc) se só houver o de
    finalizar (envio irreversível); (None, None) se não achar nenhum.
    """
    for lbl in _CONTINUE_LABELS:
        b = _visible_button(page, lbl)
        if b is not None:
            return "continue", b
    for lbl in _SUBMIT_LABELS:
        b = _visible_button(page, lbl)
        if b is not None:
            return "submit", b
    return None, None

"""Apply da Gupy — candidatura AI-driven seguindo o fluxo REAL (com travas de segurança).

→ METODOLOGIA COMPLETA (fluxo, etapas, seletores, gotchas): ver `app/platforms/gupy/GUPY.md`.
  LEIA antes de alterar o fluxo de candidatura.


Fluxo Gupy (fixo em toda Gupy; o que muda por empresa são as PERGUNTAS, que a IA responde):
  1. clicar "Candidatar-se"  (a[data-testid=apply-link])
  2. "Dados adicionais": radios indicação/colaborador (default "Não", honesto) + fonte (opcional)
     → "Salvar e continuar" (name=saveAndContinueButton)
  3. "Perguntas criadas pela empresa" → clicar "Responder agora" (aria-label)
  4. Perguntas da empresa (1ª div .curriculum-content): textareas/radios → IA responde → preenche
     → "Salvar e continuar"  ⚠️ IRREVERSÍVEL (as respostas não podem ser editadas depois)
  5. Modal → SEMPRE "Personalizar candidatura" (#dialog-save-personalization-step)
  6. "Apresente-se!": textarea de apresentação (IA) + até 3 skills (IA escolhe p/ a vaga)
     → "Finalizar candidatura"  ⚠️ ENVIO (irreversível)

Travas: pontos ⚠️ só disparam com `allow_real=True` E confirmação (`confirm()`); sem isso, o fluxo
PREENCHE tudo e PARA para revisão (dry-run). `unknown[]`/falhas também pausam (nunca chuta).

`prepare()`/`submit()` continuam para o fluxo antigo (fila/dashboard). O motor novo é
`run_auto_apply(page, ...)`, chamado por scripts/auto_apply.py (que é dono do BrowserHarness —
o plugin nunca abre browser sozinho).
"""
from __future__ import annotations

import logging

from ...ai import form_agent
from ...core.form_extract import EXTRACT_JS, to_questions
from ...core.form_fill import apply_answers, set_cv_file
from ...core.schemas import ApplyResult
from ...core.session import has_session

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- prepare/submit (fluxo antigo)
def prepare(job, application) -> ApplyResult:
    if application is None or not application.cv_pdf_path:
        return ApplyResult(ok=False, message="CV/carta não gerados. Rode tailor_job antes.")
    if not has_session("gupy"):
        return ApplyResult(ok=True, submitted=False,
                           message="Pronto para revisão, mas sem sessão Gupy — rode scripts/login.py gupy.")
    return ApplyResult(ok=True, submitted=False, message="Pronto para revisão e envio.")


def submit(job, application, *, allow_real: bool = False) -> ApplyResult:
    if not has_session("gupy"):
        return ApplyResult(ok=False, submitted=False,
                           message="Sem sessão Gupy. Rode: python scripts/login.py gupy")
    if not allow_real:
        return ApplyResult(ok=True, submitted=False,
                           message="DRY-RUN: envio real desligado (ALLOW_REAL_SUBMIT=false).")
    return ApplyResult(ok=True, submitted=False,
                       message="Envio automático: rode 'python scripts/auto_apply.py {}'.".format(job.id))


# ---------------------------------------------------------------- helpers de navegação (Gupy)
def _settle(page):
    for state in ("domcontentloaded", "networkidle"):
        try:
            page.wait_for_load_state(state, timeout=8000)
        except Exception:  # noqa: BLE001
            pass


def _click_sel(page, selector: str) -> bool:
    loc = page.locator(selector).first
    try:
        if loc.count() and loc.first.is_visible() and loc.first.is_enabled():
            loc.click()
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _try_click(page, strategies) -> bool:
    """Tenta clicar por várias estratégias: ('sel', css) | ('text', rótulo) | ('aria', rótulo)."""
    for kind, val in strategies:
        if kind == "sel" and _click_sel(page, val):
            return True
        if kind == "text" and _click_text(page, val):
            return True
        if kind == "aria" and _click_sel(page, f'[aria-label="{val}"]'):
            return True
    return False


def _sig(page) -> str:
    """Assinatura da etapa atual (url + chaves das perguntas + tipo). Muda quando a etapa troca."""
    try:
        qs = to_questions(page.evaluate(EXTRACT_JS, None))
        keys = ",".join(sorted(q.key for q in qs))
    except Exception:  # noqa: BLE001
        keys = ""
    return f"{page.url}|{keys}|{_detect_step(page)}"


def _advance(page, strategies, *, timeout_ms: int = 20000) -> bool:
    """Clica um botão de avançar e ESPERA a etapa mudar (a Gupy salva async e só então troca).
    Evita reprocessar a mesma etapa / reclcar botão que ficou desabilitado."""
    before = _sig(page)
    if not _try_click(page, strategies):
        return False
    for _ in range(max(1, timeout_ms // 500)):
        page.wait_for_timeout(500)
        if _sig(page) != before:
            _settle(page)
            return True
    _settle(page)
    return True  # tempo esgotado: segue e deixa o loop redetectar


def _click_text(page, text: str, role: str = "button") -> bool:
    loc = page.get_by_role(role, name=text, exact=False)
    try:
        n = loc.count()
    except Exception:  # noqa: BLE001
        return False
    for i in range(n):
        b = loc.nth(i)
        try:
            if b.is_visible() and b.is_enabled():
                b.click()
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _present(page, selector: str) -> bool:
    try:
        loc = page.locator(selector).first
        return loc.count() > 0 and loc.first.is_visible()
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------- detecção de etapa
_SKILLS_SEL = '[data-testid="candidate-skill"]'
_PERSONALIZE_TEXT = "#personalization-step-text-area"
_APPLY_LINK = 'a[data-testid="apply-link"]'
_RESPOND_NOW = 'button[aria-label="Responder agora"]'
_COMPANY_SCOPE = ".curriculum-content"
_INDICATED_RADIO = 'input[name="radioGroupIsIndicatedTitle"]'


def _detect_step(page) -> str:
    if _present(page, _APPLY_LINK):
        return "start"
    if _present(page, _SKILLS_SEL) or _present(page, _PERSONALIZE_TEXT):
        return "personalize"
    if _present(page, _RESPOND_NOW):
        return "respond_now"
    if _present(page, _COMPANY_SCOPE) and page.locator(f"{_COMPANY_SCOPE} textarea, {_COMPANY_SCOPE} input").count():
        return "company"
    if _present(page, _INDICATED_RADIO):
        return "dados"
    return "advance"  # etapa intermediária (revisão de currículo): só seguir


# ---------------------------------------------------------------- motor da candidatura
def run_auto_apply(page, *, job, application, master_cv, extras, cover,
                   allow_real: bool, confirm, log_fn, max_steps: int = 14) -> dict:
    """Dirige a candidatura na Gupy. `confirm()->bool` autoriza ações irreversíveis;
    `log_fn(str)` reporta o progresso. Retorna {outcome, filled, unknown}."""
    job_d = {"title": job.title, "company": job.company, "description": job.description}
    filled: list[dict] = []
    all_unknown: list[str] = []
    cv_uploaded = False

    def answer_and_fill(questions, *, scope_label: str) -> tuple[list, list]:
        nonlocal filled, all_unknown
        plan = form_agent.map_form(questions, profile=master_cv, cover_letter=cover,
                                   job=job_d, extras=extras)
        for a in plan.answers:
            log_fn(f"      → {a.key!r} = {a.value[:70]!r} ({a.confidence})")
            filled.append({"step": scope_label, "key": a.key, "value": a.value})
        if plan.unknown:
            log_fn(f"      🔒 unknown: {plan.unknown}")
            all_unknown.extend(plan.unknown)
        failed = apply_answers(page, questions, plan.answers)
        if failed:
            log_fn(f"      ! não preenchi: {failed}")
        return plan.unknown, failed

    page.goto(job.url, wait_until="domcontentloaded")
    _settle(page)

    for step in range(max_steps):
        kind = _detect_step(page)
        log_fn(f"\n[{step}] etapa detectada: {kind}  ({page.url})")

        if kind == "start":
            if not _advance(page, [("sel", _APPLY_LINK), ("sel", 'a:has-text("Candidatar-se")')]):
                return {"outcome": "error", "filled": filled, "unknown": all_unknown,
                        "message": "não achei 'Candidatar-se'."}
            continue

        if kind == "dados":
            # radios já vêm em "Não" (honesto); fonte é opcional → mantemos e só avançamos.
            log_fn("   dados adicionais: mantendo defaults (Não/Não), fonte opcional em branco.")
            if not _advance(page, [("sel", 'button[name="saveAndContinueButton"]'),
                                   ("text", "Salvar e continuar")]):
                return {"outcome": "error", "filled": filled, "unknown": all_unknown,
                        "message": "não achei 'Salvar e continuar' em dados adicionais."}
            continue

        if kind == "respond_now":
            _advance(page, [("aria", "Responder agora"), ("text", "Responder agora")])
            continue

        if kind == "company":
            snap = page.evaluate(EXTRACT_JS, _COMPANY_SCOPE)
            questions = to_questions(snap)
            log_fn(f"   perguntas da empresa ({len(questions)}):")
            for q in questions:
                log_fn(f"      • [{q.kind}] req={q.required} :: {q.prompt[:80]!r}")
            unknown, failed = answer_and_fill(questions, scope_label="company")
            # ⚠️ "Salvar e continuar" aqui é IRREVERSÍVEL.
            if unknown or failed:
                return {"outcome": "needs_review", "filled": filled, "unknown": all_unknown,
                        "message": "perguntas da empresa com pendências — revise antes de salvar (irreversível)."}
            if not allow_real:
                return {"outcome": "dry_run", "filled": filled, "unknown": all_unknown,
                        "message": "DRY-RUN: perguntas preenchidas; NÃO cliquei em 'Salvar e continuar' "
                                   "(passo irreversível). Rode com --real para enviar de verdade."}
            if not confirm("Salvar as respostas da empresa? NÃO poderão ser editadas depois."):
                return {"outcome": "cancelled", "filled": filled, "unknown": all_unknown,
                        "message": "cancelado antes de salvar as perguntas da empresa."}
            log_fn("   → clicando 'Salvar e continuar' (irreversível, confirmado)…")
            _advance(page, [("text", "Salvar e continuar")])
            # modal → sempre personalizar
            if not (_click_sel(page, "#dialog-save-personalization-step")
                    or _click_text(page, "Personalizar candidatura")):
                log_fn("   (modal de personalização não apareceu; seguindo)")
            _settle(page)
            page.wait_for_timeout(1200)
            continue

        if kind == "personalize":
            # upload do CV sob medida, se houver input de arquivo nesta etapa
            if not cv_uploaded and set_cv_file(page, application.cv_pdf_path):
                cv_uploaded = True
                log_fn("   ✓ CV enviado (upload).")
            snap = page.evaluate(EXTRACT_JS, None)
            questions = to_questions(snap)
            log_fn(f"   apresente-se + skills ({len(questions)}):")
            for q in questions:
                extra = f" (até {q.max_select})" if q.kind == "skills" else ""
                log_fn(f"      • [{q.kind}{extra}] :: {q.prompt[:70]!r}")
            unknown, failed = answer_and_fill(questions, scope_label="personalize")
            # ⚠️ "Finalizar candidatura" = ENVIO.
            if not allow_real:
                return {"outcome": "dry_run", "filled": filled, "unknown": all_unknown,
                        "message": "DRY-RUN: apresentação/skills preenchidas; NÃO enviei."}
            if not confirm("Finalizar e ENVIAR a candidatura?"):
                return {"outcome": "cancelled", "filled": filled, "unknown": all_unknown,
                        "message": "cancelado antes de finalizar."}
            if not _click_text(page, "Finalizar candidatura"):
                return {"outcome": "error", "filled": filled, "unknown": all_unknown,
                        "message": "não achei 'Finalizar candidatura'."}
            _settle(page)
            return {"outcome": "sent", "filled": filled, "unknown": all_unknown,
                    "message": "candidatura finalizada."}

        # etapa intermediária (revisão de currículo): tentar avançar
        if _advance(page, [("text", "Continuar"), ("sel", 'button[name="saveAndContinueButton"]'),
                           ("text", "Salvar e continuar"), ("text", "Avançar"), ("text", "Próximo")]):
            log_fn("   avançando etapa intermediária.")
            continue
        return {"outcome": "incomplete", "filled": filled, "unknown": all_unknown,
                "message": f"etapa '{kind}' sem ação conhecida; parei para inspeção."}

    return {"outcome": "incomplete", "filled": filled, "unknown": all_unknown,
            "message": "excedi o máximo de etapas."}

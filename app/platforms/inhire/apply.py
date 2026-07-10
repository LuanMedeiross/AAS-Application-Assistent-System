"""InHire apply — AI-driven, following the REAL inline-form flow (with safety gates).

→ FULL METHODOLOGY (flow, steps, selectors, gotchas): see `app/platforms/inhire/INHIRE.md` (§3).
  READ it before changing this flow.

InHire flow (per-job fields VARY, same as Gupy — we extract the form dynamically and let the AI
answer, instead of hardcoding a field set):
  0. goto `https://<tenant>.inhire.app/vagas/{jobId}/{slug}`  (anonymous; stealth on — the title slug
     is REQUIRED, a bare /vagas/{id} renders a black screen). The apply `<form JobForm>` is INLINE.
  1. "Informações" (step 1): identity (name/email/phone/linkedin/city) + per-job standard fields
     (workModel, salary, referral…) + CV upload (input[name=resume]) → button "Avançar".
  2. "Diversidade" (step 2): optional diversity self-ID + REQUIRED LGPD consent checkbox
     → button "Continuar inscrição"  ⚠️ IRREVERSIBLE SUBMIT (creates the job-talent, POST /job-talents/).

The submit is gated by invisible reCAPTCHA v3 (auto-executed in the browser) — the reason this is a
browser-channel apply, not a raw API POST. "Avançar" (step 1→2) is reversible navigation; only
"Continuar inscrição" is irreversible.

Safety: the ⚠️ submit only fires with `allow_real=True` AND `confirm()`; otherwise the flow FILLS
everything (both steps) and STOPS (dry-run). `unknown[]`/fill failures pause too (never guess).

The engine is `run_auto_apply(page, ...)`, called by the UI (via `app.services.apply_application`) —
owner of the BrowserHarness; the plugin never opens a browser itself.
"""
from __future__ import annotations

import logging

from ...ai import form_agent
from ...core.form_extract import EXTRACT_JS, to_questions
from ...core.form_fill import apply_answers, set_cv_file

log = logging.getLogger(__name__)

# The inline apply form. Scope extraction/queries to it so we ignore the job description, the
# accessibility widgets (Hand Talk), Intercom, etc. Emotion CSS classes are build-hashed → we key
# on data-component-name / field name= / button text, never on css-* classes. See INHIRE.md §3.
_FORM_SEL = 'form[data-component-name="JobForm"]'

# Buttons (matched by accessible text, not class):
_ADVANCE_LABELS = ("Avançar", "Próximo", "Continuar inscrição")  # step 1→2 (reversible)
_SUBMIT_LABEL = "Continuar inscrição"                            # ⚠️ irreversible submit (step 2)
# CTAs that only reveal/scroll to the form (safe to click; never the submit):
_REVEAL_LABELS = ("Candidatar-se para a vaga", "Candidatar")

# Success markers after submit (⚠️ HEURISTIC — the exact confirmation copy is still to be captured in
# a supervised real submit; see INHIRE.md §5 open items). Kept broad + guarded by allow_real/confirm.
_DONE_MARKERS = ("inscrição realizada", "candidatura enviada", "candidatura recebida",
                 "recebemos sua", "obrigado por se candidatar", "aplicação enviada",
                 "sua candidatura foi", "inscrição enviada")


# ---------------------------------------------------------------- navigation helpers
def _settle(page):
    for state in ("domcontentloaded", "networkidle"):
        try:
            page.wait_for_load_state(state, timeout=8000)
        except Exception:  # noqa: BLE001
            pass


def _wait_form(page, timeout_ms: int = 20000) -> bool:
    """Wait for the inline JobForm to hydrate (the SPA mounts it client-side)."""
    try:
        page.wait_for_selector(_FORM_SEL, timeout=timeout_ms)
        return True
    except Exception:  # noqa: BLE001
        return False


def _visible_enabled_button(page, label: str):
    """First visible+enabled <button> whose accessible name contains `label` (exact=False)."""
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


def _reveal_form(page) -> None:
    """Best-effort: click a reveal CTA so the form is active/scrolled into view. Never the submit."""
    for label in _REVEAL_LABELS:
        if label == _SUBMIT_LABEL:  # defensive: never treat the submit as a reveal
            continue
        b = _visible_enabled_button(page, label)
        if b is not None:
            try:
                b.click()
                _settle(page)
                return
            except Exception:  # noqa: BLE001
                pass


def _advance_button(page):
    """The step-advance button (reversible). Excludes the irreversible submit label."""
    for label in _ADVANCE_LABELS:
        if label == _SUBMIT_LABEL:
            continue
        b = _visible_enabled_button(page, label)
        if b is not None:
            return b
    return None


def _text_has(page, needles) -> bool:
    try:
        txt = page.evaluate("() => (document.body.innerText || '').toLowerCase()")
    except Exception:  # noqa: BLE001
        return False
    return any(n in txt for n in needles)


def _check_required_consents(page) -> None:
    """Tick any unchecked checkbox inside the form (LGPD/consent). These are always "agree" and the
    submit stays disabled until checked. Uses a real click so React registers the change."""
    js = r"""
    (formSel) => {
      const form = document.querySelector(formSel); if (!form) return 0;
      let n = 0;
      form.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        if (!cb.checked) { (cb.closest('label') || cb).click(); n++; }
      });
      return n;
    }
    """
    try:
        page.evaluate(js, _FORM_SEL)
    except Exception:  # noqa: BLE001
        pass


def _sent_confirmation(page, timeout_ms: int = 20000) -> bool:
    """Wait for a post-submit success signal. ⚠️ HEURISTIC (markers unconfirmed) — we wait for a
    success marker OR the form to disappear. A started-but-unconfirmed submit is a FAILURE, not a
    success (mirror Gupy's anti-false-positive rule)."""
    markers = " || ".join(f"t.includes('{m}')" for m in _DONE_MARKERS)
    js = ("() => { const t=(document.body.innerText||'').toLowerCase();"
          f" if ({markers}) return true;"
          f" return !document.querySelector('{_FORM_SEL}'); }}")
    try:
        page.wait_for_function(js, timeout=timeout_ms)
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------- apply engine
def run_auto_apply(page, *, job, application, master_cv, extras, cover,
                   allow_real: bool, confirm, log_fn, max_steps: int = 6) -> dict:
    """Drive the InHire apply. `confirm()->bool` authorizes the irreversible submit; `log_fn(str)`
    reports progress. Returns {outcome, message, filled, unknown, qa}. Same generic engine as Gupy:
    extract the current step's fields, let the AI answer, fill, upload the CV, then advance/submit."""
    job_d = {"title": job.title, "company": job.company, "description": job.description}
    filled: list[dict] = []
    all_unknown: list[str] = []
    qa: list[dict] = []
    cv_uploaded = False

    def answer_and_fill(questions, *, scope_label: str) -> tuple[list, list]:
        nonlocal filled, all_unknown, qa
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
        # Transparency record: what the AI said in the user's name (skip file uploads — not AI Q&A).
        answers_by_key = {a.key: a for a in plan.answers}
        failed_set, unknown_set = set(failed), set(plan.unknown)
        for q in questions:
            if q.kind == "file":
                continue
            ans = answers_by_key.get(q.key)
            if q.key in failed_set:
                status, value, confidence = "failed", (ans.value if ans else ""), \
                    (ans.confidence if ans else "")
            elif ans is not None:
                status, value, confidence = "answered", ans.value, ans.confidence
            elif q.key in unknown_set:
                status, value, confidence = "unknown", "", ""
            else:
                status, value, confidence = "skipped", "", ""
            qa.append({"step": scope_label, "key": q.key, "question": q.prompt, "kind": q.kind,
                       "required": q.required, "options": q.options, "max_select": q.max_select,
                       "answer": value, "confidence": confidence, "status": status})
        return plan.unknown, failed

    page.goto(job.url, wait_until="domcontentloaded")
    _settle(page)
    if not _wait_form(page):
        return {"outcome": "error", "filled": filled, "unknown": all_unknown, "qa": qa,
                "message": "formulário de candidatura não carregou (SPA não montou o JobForm)."}
    _reveal_form(page)

    for step in range(max_steps):
        # Already applied / confirmation already on screen (e.g. a re-run).
        if _text_has(page, _DONE_MARKERS):
            return {"outcome": "already_applied", "filled": filled, "unknown": all_unknown, "qa": qa,
                    "message": "candidatura já aparece como enviada."}

        snap = page.evaluate(EXTRACT_JS, _FORM_SEL)
        questions = to_questions(snap)
        log_fn(f"\n[{step}] campos da etapa ({len(questions)}):")
        for q in questions:
            log_fn(f"      • [{q.kind}] req={q.required} :: {q.prompt[:80]!r}")

        unknown, failed = answer_and_fill(questions, scope_label=f"step{step}")

        # Upload the tailored CV into the file input (input[name=resume], hidden but set_input_files
        # works). Manifest is cv:"file" → application.cv_pdf_path is rendered and ready.
        if not cv_uploaded and application.cv_pdf_path and set_cv_file(page, application.cv_pdf_path):
            cv_uploaded = True
            log_fn("   ✓ CV anexado (upload).")

        _check_required_consents(page)

        # Pendências ANTES de qualquer passo (avançar OU enviar): pausa para revisão humana.
        if unknown or failed:
            return {"outcome": "needs_review", "filled": filled, "unknown": all_unknown, "qa": qa,
                    "message": f"etapa com pendências (unknown={unknown}, falhou={failed}); "
                               "revise antes de continuar."}

        advance = _advance_button(page)
        submit = _visible_enabled_button(page, _SUBMIT_LABEL)

        # Prefer advancing while a (reversible) "Avançar" is still available — submit is last resort.
        if advance is not None:
            log_fn("   → avançando etapa (reversível).")
            try:
                advance.click()
            except Exception as e:  # noqa: BLE001
                return {"outcome": "error", "filled": filled, "unknown": all_unknown, "qa": qa,
                        "message": f"falha ao clicar em avançar: {e}"}
            _settle(page)
            page.wait_for_timeout(800)
            continue

        if submit is not None:
            # ⚠️ IRREVERSIBLE: "Continuar inscrição" creates the job-talent.
            if not allow_real:
                return {"outcome": "dry_run", "filled": filled, "unknown": all_unknown, "qa": qa,
                        "message": "DRY-RUN: formulário preenchido e CV anexado; NÃO cliquei em "
                                   "'Continuar inscrição' (envio irreversível). Rode com --real para enviar."}
            if not confirm("Enviar a candidatura na InHire? (irreversível)"):
                return {"outcome": "cancelled", "filled": filled, "unknown": all_unknown, "qa": qa,
                        "message": "cancelado antes do envio."}
            log_fn("   → clicando 'Continuar inscrição' (envio irreversível, confirmado)…")
            try:
                submit.click()
            except Exception as e:  # noqa: BLE001
                return {"outcome": "error", "filled": filled, "unknown": all_unknown, "qa": qa,
                        "message": f"falha ao clicar no envio: {e}"}
            # ⚠️ Do NOT report 'sent' just for clicking — wait for the confirmation (anti-false-positive).
            if _sent_confirmation(page):
                return {"outcome": "sent", "filled": filled, "unknown": all_unknown, "qa": qa,
                        "message": "candidatura enviada (confirmação heurística — validar marcador real)."}
            return {"outcome": "error", "filled": filled, "unknown": all_unknown, "qa": qa,
                    "message": "cliquei em 'Continuar inscrição' mas não vi confirmação — envio pode "
                               "ter ficado INCOMPLETO (não marquei como enviada)."}

        # Neither advance nor submit is enabled → a required field is still unfilled (or the layout
        # changed). Stop for inspection instead of guessing.
        return {"outcome": "incomplete", "filled": filled, "unknown": all_unknown, "qa": qa,
                "message": "sem botão de avançar/enviar habilitado (campo obrigatório pendente?); parei."}

    return {"outcome": "incomplete", "filled": filled, "unknown": all_unknown, "qa": qa,
            "message": "excedi o máximo de etapas."}

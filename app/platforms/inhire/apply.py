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
import re

from ...ai import form_agent
from ...core.form_extract import EXTRACT_JS, FormQuestion, to_questions
from ...core.form_fill import apply_answers, set_cv_file

log = logging.getLogger(__name__)

# Location fields are custom `react-dropdown-select` widgets (country/phoneCountry) + a city control
# that MORPHS by country (plain `#district` input, or `#districtBr` dropdown for Brazil). The generic
# form_extract can't see them (not <select>/<input>), so we handle the whole block here and EXCLUDE
# these keys from the generic AI fill (otherwise the AI answers the merged "País/Cidade" prompt wrong).
# `phone` is also handled here: the "Celular com DDD" field rejects the "+55 " country prefix (that
# belongs in phoneCountry), so we fill the NATIONAL number and leave the country code to the dropdown.
_LOCATION_KEYS = {"country", "phoneCountry", "district", "districtBr", "phone"}


def _national_phone(phone: str) -> str:
    """DDD + number as DIGITS ONLY: drop the "+<code>" country prefix (that belongs in phoneCountry)
    and any mask chars (spaces/dashes/parens) — the masked field re-formats the raw digits itself."""
    national = re.sub(r"^\s*\+\d{1,3}[\s-]*", "", phone or "")
    return re.sub(r"\D", "", national)

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


def _wait_step_button(page, *, tries: int = 10, interval_ms: int = 500):
    """Poll for the step's advance/submit button to become ENABLED. React validates asynchronously
    after the last field is filled, so we wait instead of reading the button state immediately.
    Returns (advance_btn_or_None, submit_btn_or_None)."""
    for _ in range(tries):
        adv = _advance_button(page)
        sub = _visible_enabled_button(page, _SUBMIT_LABEL)
        if adv is not None or sub is not None:
            return adv, sub
        page.wait_for_timeout(interval_ms)
    return None, None


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


def _select_dropdown(page, name, want: str, *, timeout_ms: int = 6000) -> bool:
    """Drive a react-dropdown-select `[name=...]`: open it, type `want` in the 'Pesquisar' search,
    click the matching option. Returns True on selection. (Verified on InHire country/city widgets.)"""
    want = (want or "").strip()
    if not want:
        return False
    cont = page.locator(f'[name="{name}"]').first
    try:
        if not cont.count():
            return False
        opener = cont.locator('[aria-label="Dropdown select"]').first
        (opener if opener.count() else cont).click()
        page.wait_for_timeout(400)
        search = cont.locator('input[placeholder="Pesquisar"]').first
        if search.count():
            search.fill(want)
            page.wait_for_timeout(600)
        opt = page.locator('.react-dropdown-select-dropdown').get_by_text(want, exact=False).first
        if opt.count():
            opt.click()
            page.wait_for_timeout(400)
            return True
        page.keyboard.press("Escape")  # close so the panel doesn't overlay other controls
    except Exception as e:  # noqa: BLE001
        log.warning("dropdown %s: %s", name, e)
    return False


def _fill_location(page, *, master_cv, extras, job_d, cover, log_fn) -> tuple[list, list]:
    """Fill the InHire location block (country + city, and phoneCountry best-effort). The AI gives us
    clean country/city values (its merged DOM prompt is unreliable), then we drive the dropdowns.
    Returns (filled_records, failed_keys). No-op when the job has no country widget."""
    filled: list = []

    # Phone: fill the national number (the +55 country code lives in phoneCountry). Always, even when
    # the job has no country widget (the phone field is a standard InHire field).
    phone_val = _national_phone(master_cv.get("phone", ""))
    if phone_val:
        ploc = page.locator('input[name="phone"]').first
        try:
            if ploc.count() and ploc.is_editable(timeout=2000):
                ploc.fill(phone_val)
                filled.append({"step": "location", "key": "phone", "value": phone_val})
                log_fn(f"      → phone = {phone_val!r}")
        except Exception:  # noqa: BLE001
            pass

    if not page.locator('[name="country"]').count():
        return filled, []
    qs = [
        FormQuestion(key="__country__", kind="text", required=True,
                     prompt="Em qual PAÍS você mora? Responda só o nome do país (ex.: Brasil)."),
        FormQuestion(key="__city__", kind="text", required=True,
                     prompt="Em qual CIDADE você mora? Responda só o nome da cidade (ex.: São Paulo)."),
    ]
    plan = form_agent.map_form(qs, profile=master_cv, cover_letter=cover, job=job_d, extras=extras)
    vals = {a.key: a.value.strip() for a in plan.answers}
    country, city = vals.get("__country__", ""), vals.get("__city__", "")

    if not (country and _select_dropdown(page, "country", country)):
        return filled, ["country"]
    filled.append({"step": "location", "key": "country", "value": country})
    log_fn(f"      → country = {country!r}")
    _select_dropdown(page, "phoneCountry", country)  # best-effort (usually pre-defaulted → ignore)

    page.wait_for_timeout(400)  # let the city control re-render for the chosen country
    if city and _select_dropdown(page, "districtBr", city):
        filled.append({"step": "location", "key": "city", "value": city})
        log_fn(f"      → city = {city!r}")
        return filled, []
    # non-Brazil: a plain #district input becomes editable after the country is set
    dist = page.locator("#district").first
    try:
        if city and dist.count() and dist.is_editable(timeout=2000):
            dist.fill(city)
            filled.append({"step": "location", "key": "city", "value": city})
            log_fn(f"      → city = {city!r}")
            return filled, []
    except Exception:  # noqa: BLE001
        pass
    return filled, ["city"]


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
        # Location widgets are handled separately (see _LOCATION_KEYS) — exclude them from the AI fill.
        questions = [q for q in to_questions(snap) if q.key not in _LOCATION_KEYS]
        log_fn(f"\n[{step}] campos da etapa ({len(questions)}):")
        for q in questions:
            log_fn(f"      • [{q.kind}] req={q.required} :: {q.prompt[:80]!r}")

        unknown, failed = answer_and_fill(questions, scope_label=f"step{step}")

        # InHire location block (country/city/phone-country custom dropdowns), if present this step.
        loc_filled, loc_failed = _fill_location(page, master_cv=master_cv, extras=extras,
                                                job_d=job_d, cover=cover, log_fn=log_fn)
        filled.extend(loc_filled)
        failed = list(failed) + loc_failed

        # Upload the tailored CV into the file input (input[name=resume], hidden but set_input_files
        # works). Manifest is cv:"file" → application.cv_pdf_path is rendered and ready.
        if not cv_uploaded and application.cv_pdf_path and set_cv_file(page, application.cv_pdf_path):
            cv_uploaded = True
            log_fn("   ✓ CV anexado (upload).")

        _check_required_consents(page)

        # Wait for React to finish validating and enable the step button (async after the last fill).
        advance, submit = _wait_step_button(page)

        # The form's OWN validation is the source of truth: React only enables "Avançar"/"Continuar
        # inscrição" once every REQUIRED field is satisfied. So we don't hard-block on unknown/failed
        # (those left a field BLANK, never wrote wrong data) — if a required one is missing, the button
        # stays disabled and we fall through to needs_review below. This tolerates the AI declining a
        # NON-required field (e.g. isIndication) without wrongly aborting a valid application.

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

        # Neither advance nor submit is enabled → a required field is still unfilled. If we know which
        # ones the AI couldn't answer/fill, surface them (needs_review); otherwise it's a layout/other
        # gap (incomplete). Either way we stop — never guess, never submit.
        if unknown or failed:
            return {"outcome": "needs_review", "filled": filled, "unknown": all_unknown, "qa": qa,
                    "message": f"botão desabilitado com pendências (unknown={unknown}, falhou={failed}); "
                               "revise/complete os campos obrigatórios."}
        return {"outcome": "incomplete", "filled": filled, "unknown": all_unknown, "qa": qa,
                "message": "sem botão de avançar/enviar habilitado (campo obrigatório pendente?); parei."}

    return {"outcome": "incomplete", "filled": filled, "unknown": all_unknown, "qa": qa,
            "message": "excedi o máximo de etapas."}

---
name: diagnose-gupy
description: >-
  Methodology for diagnosing and fixing failures in Gupy's automatic application flow
  (app/platforms/gupy/apply.py + core/form_extract + form_fill + ai/form_agent). Use ALWAYS when
  an application ends up in needs_review, incomplete, error, or is a FALSE POSITIVE (reported as
  submitted without finalizing). Encodes the scraping techniques, the catalog of known causes
  (A–G + finalize), the DOM dump snippets, the safety rules (idempotency) and the pitfalls
  already resolved — so you don't relearn or regress. Validated: took 19 applications from
  ~13 false positives to 18 confirmed by Gupy, fixing 7 causes.
---

# Diagnosing Gupy's application flow

> Complements `app/platforms/gupy/GUPY.md` (mechanics) with the **diagnostic method**. When a
> job doesn't finalize correctly, follow this instead of trying to guess.

## When to use
- Application ended up in `needs_review` / `incomplete` / `error`.
- **False positive**: reported "sent" but Gupy's panel shows it started and **not finalized**.
- Different behavior between batch (headless/concurrent) and single run (headed).

## Safety rules (READ FIRST)
1. **Gupy is IDEMPOTENT**: re-applying resumes the **SAME `application id`** (verified — the id
   in the URL `/applications/<id>/` doesn't change). So **re-running the apply does NOT duplicate**
   the application → diagnosing/reconciling directly on the real job is safe.
2. **Gupy does NOT mark "already applied" on the public link**: the `jobUrl` of an already-submitted
   job still shows "Apply" and `_detect_step` returns `start`. Don't rely on this for "already applied".
3. **NEVER report `sent` without confirmation**: only after the `"Application finalized!"` /
   "Track application" screen (`_finalized_ok`). A false positive = FAILURE in production.
4. **Test DIRECTLY on the problem job** (Gupy's state gets "dirty" — auto-saved and
   disabled fields). Reproducing on another job hides the bug.

## Method (5 steps)
1. **Reproduce the flow on the job itself**, headless, capturing the log:
   navigate via the plugin helpers (`ga._detect_step`, `ga._advance`, `ga._APPLY_LINK`,
   `ga._COMPANY_SCOPE`) up to the failing step; pass a `log_fn=lista.append` to
   `run_auto_apply` OR replicate the loop and print each stage (`[i] etapa: {kind}`).
2. **Dump the DOM state at the failing step** (this is where the bug appears). For each field:
   `disabled`, `readonly`, `value`, `checked`, `aria-required`. For buttons: `text`, `disabled`,
   `data-testid`. And: `[role=dialog]`/modals and `.error-message`/`[role=alert]`. Snippets below.
3. **Compare what the agent answered vs what failed**: run `to_questions` + `form_agent.map_form`
   + `apply_answers` and print `plan.answers`, `plan.unknown` and the returned `failed`.
4. **Match against the catalog of causes** (below) and find the right LAYER of the fix
   (extract / fill / agent / apply).
5. **Fix, re-test on the SAME job** (should give `failed=[]` / `unknown=[]`), then reconcile
   (`scripts/reconcile_applied.py --threads N`).

## Catalog of known causes
| Code | Symptom | Cause | Layer / Fix |
|---|---|---|---|
| **A** | `.fill()` hangs 30s; `<textarea disabled>valor</textarea>` | Gupy auto-saves and **disables** the answered field; on re-run we try to rewrite it | `core/form_fill.apply_answers`: if `is_editable()` is false → already answered (OK if it has a value); `fill(timeout=10000)` |
| **B** | one option becomes `unknown`; names `checkbox-XXXX-0/1/2` | single-choice checkbox with **indexed names** → each one became a separate question | `core/form_extract.to_questions`: groups by base name `re.sub(r'-\d+$','',name)`; `form_fill` clicks by prefix `name^="base-"` |
| **C** | field filled with `"unknown"`/"não sei"; or RG/CPF | model wrote garbage answers for personal data we don't have | `ai/form_agent._sanitize`: `_NON_ANSWERS` → becomes `unknown` (doesn't write). Prompt: missing personal data → `unknown`, never write "unknown" |
| **D** | 40+ questions, same question repeated ~30x | huge internal recruitment form (Vivo) with an "exploded" radio/checkbox group | same fix as B; and personal data is missing (RG) → see EXTRAS/Preferences |
| **E** | loop `etapa: advance` (heading "Dados adicionais"); radio not pre-selected | company only has `radioGroupIsCompanyEmployeeTitle` (without the referral one) → `_detect_step` didn't see "dados" and the save doesn't advance without the radio answered in React | `gupy/apply.py`: `_DADOS_RADIOS` (detects by either of the two radios) + **Playwright's `.click(force=True)`** on the "No" label (a JS click does NOT fire React's onChange, even with the radio HTML-checked) |
| **F** | `failed` on an EMPTY, enabled field; `name` contains `"`/quotes | selector `[name="...\"...\""]` breaks with embedded quotes → `_locate_text` can't find it | `core/form_fill._locate_text`: escape `"`/`\`; fallback by INDEX via JS (`findIndex` + `.nth(idx)`) |
| **G** | after saving the dados the step does NOT change; no error/empty-field; `saveDisabled=false` | company **WITHOUT question form** → the save opens DIRECTLY the **"Personalize application" modal**, which overlays the dados form in the DOM → `_detect_step` sees "dados" again | `gupy/apply.py`: the modal is its own STEP — `_PERSONALIZE_MODAL='#dialog-save-personalization-step'` → `kind='modal'` → click "Personalizar" (covers with/without company questions) |
| **Finalize** | reported `sent` but didn't finalize | we closed the browser before the submit completed (headless/load) | `gupy/apply.py._finalized_ok`: waits for "Application finalized!" before `sent`; otherwise `error` |

## Dump snippets (reuse)
State of the fields within the company questions scope (`.curriculum-content`):
```js
() => { const norm=s=>(s||'').replace(/\s+/g,' ').trim();
  const scope=document.querySelector('.curriculum-content')||document;
  return [...scope.querySelectorAll('input,textarea,select')].map(el=>({
    tag:el.tagName.toLowerCase(), type:el.getAttribute('type')||'',
    name:(el.getAttribute('name')||'').slice(0,55), disabled:!!el.disabled, readonly:!!el.readOnly,
    value:norm((el.value??'').toString()).slice(0,30), ariaReq:el.getAttribute('aria-required'),
    checked:el.checked })); }
```
Buttons + modals + errors (any screen, e.g. finalize):
```js
() => { const norm=s=>(s||'').replace(/\s+/g,' ').trim();
  const vis=el=>{const r=el.getBoundingClientRect();const s=getComputedStyle(el);return s.display!=='none'&&s.visibility!=='hidden'&&(r.width+r.height)>0;};
  return { url:location.href, heading:norm((document.querySelector('main h1,main h2')||{}).innerText||''),
    buttons:[...document.querySelectorAll('button,[role=button],a[data-testid]')].filter(vis).map(b=>({text:norm(b.innerText).slice(0,45),disabled:!!b.disabled,testid:b.getAttribute('data-testid')||''})),
    dialogs:[...document.querySelectorAll('[role=dialog],[class*=modal i],[class*=Dialog]')].filter(vis).map(d=>norm(d.innerText).slice(0,240)),
    errors:[...document.querySelectorAll('.error-message,[role=alert]')].map(e=>norm(e.innerText)).filter(t=>t.length>1&&t.length<160) }; }
```

## Diagnostic script skeleton
```python
from app.core.browser import BrowserHarness
from app.platforms.gupy import apply as ga
from app.core.form_extract import EXTRACT_JS, to_questions
from app.core.form_fill import apply_answers
from app.ai import form_agent
# ... carregar job/app_row/profile ...
with BrowserHarness(headless=True) as h:
    ctx=h.new_context('gupy'); page=ctx.new_page(); page.goto(job.url); ga._settle(page)
    for i in range(14):
        kind=ga._detect_step(page)
        if kind in ('company','personalize','modal','done'): break   # pare no passo que quer inspecionar
        if kind=='start': ga._advance(page,[('sel',ga._APPLY_LINK)])
        elif kind=='dados': ga._advance(page,[('sel','button[name=\"saveAndContinueButton\"]'),('text','Salvar e continuar')])
        elif kind=='respond_now': ga._advance(page,[('aria','Responder agora'),('text','Responder agora')])
        else:
            if not ga._advance(page,[('text','Continuar'),('text','Salvar e continuar')]): print('travou',kind); break
    print(page.evaluate(STATE_JS))                     # <- estado dos campos
    qs=to_questions(page.evaluate(EXTRACT_JS, ga._COMPANY_SCOPE))
    plan=form_agent.map_form(qs, profile=cv, cover_letter=cover, job=job_d, extras=extras)
    print('failed=', apply_answers(page, qs, plan.answers), 'unknown=', plan.unknown)
    ctx.close()
```

## Wins & pitfalls (war memory)
- ✖➜✔ **Diagnostic error that almost became "unfixable":** in Cause G I declared the job a
  "broken career page" because the save wouldn't advance and there was no error/empty-field. **I was wrong** —
  it was a MODAL I hadn't dumped. **Golden lesson: always include `[role=dialog]`/modals in the
  dump BEFORE concluding "anomalous page".** If the step doesn't change but there's no error or empty field,
  it's a modal (or overlay), not a defect.
- ✔ **Headed vs headless** was the key to the false positive: headed finalized, headless didn't → the
  problem was not waiting for the confirmation, not the navigation code.
- ✔ Confirming **idempotency** (same application id) BEFORE reconciling in bulk avoided a
  double-submit panic.
- ✖ Don't trust `applicationDeadline`/badges for status (see GUPY.md). Nor "already applied"
  on the jobUrl.
- ✖ `.fill()` default = 30s: on a disabled field it hangs the whole flow. Always a short timeout.
- ✖ Re-running the diagnostic on an already-touched job shows dirty state (disabled fields) — interpret
  it as a signal, not as a new bug.
- ✔ Run in `--dry-run`/dump before any irreversible click ("Salvar e continuar" of the
  company questions and "Finalizar" hang/submit).

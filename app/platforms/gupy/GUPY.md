# GUPY — Plugin playbook (READ BEFORE TOUCHING)

> **Source of truth for the Gupy methodology.** Consult this file whenever you are about to change
> `discovery.py`, `apply.py` or `manifest.py`. Empirical findings (2026) — revalidate if Gupy
> changes. Complements `docs/PLATFORMS.md` (multi-platform overview) and `CLAUDE.md` (rules).

Channel: **`api`** for discovery (anonymous HTTP, no captcha) + **`browser`** for the application
(requires the candidate's logged-in session). The plugin **does not open a browser on its own** — it
receives `page`/`session` from the harness (`scripts/auto_apply.py` owns the `BrowserHarness`).

---

## 1. Job discovery (API channel, anonymous)

**Endpoint:** `GET https://employability-portal.gupy.io/api/v1/jobs`
(this is the public backend of `portal.gupy.io`; it is **not** `api.gupy.io`, which requires a company Bearer.)

**Response:** `{ "data": [ {job}, ... ], "pagination": {total, limit, offset} }`

### Parameters (empirical study)
| Param | Effect | Note |
|---|---|---|
| `jobName` | text search on the title | **it's `jobName`, not `name`** (`name` → HTTP 400) |
| `limit` | page size | **max. 100** (`>100` → returns empty) |
| `offset` | pagination | add `limit` until exhausted |
| `workplaceType` | `remote` \| `hybrid` \| `on-site` | filters server-side, **1 value per request** |
| `isRemoteWork` | `true` | == `workplaceType=remote` |
| `state` | FULL name ("São Paulo") | "SP" → 0 results |
| `city` | city name | |
| `type` | `vacancy_type_effective` \| `..._internship` \| `..._talent_pool` \| `..._temporary` \| `..._associate` \| `vacancy_legal_entity` | filters by job type |

**There are NO** date/ordering filters: `orderBy`, `sort`, `publishedSince` → **HTTP 400**.

### ⚠️ `pagination.total` is BROKEN
It reports only the page size (capped at `limit`), not the real total. E.g.: "segurança da
informação" with `limit=100` → `total:100`, but `offset=100` brings +38 more (real ≈138).
**Rule: paginate by `offset` until `len(data) < limit`.** (See `_fetch_all()`.)

### Fields of each job (→ `JobPosting`)
`id`, `companyId`, `name` (title), `description` (**HTML** — clean it), `careerPageId`,
`careerPageName` (company), `careerPageUrl`, `type`, `publishedDate` (ISO), `applicationDeadline`
(date), `isRemoteWork`, `city`, `state`, `country`, `jobUrl` (direct link), `workplaceType`,
`disabilities`, `skills`, `badges` (not always present).

Map: `platform="gupy"`, `external_id=id`, `title=name`, `company=careerPageName`, `url=jobUrl`,
`location=city/state/country` (or "Remoto"), `description=cleaned`, `raw=<raw object>`.

**Detail endpoint:** `GET /api/v1/jobs/{id}` — same fields, **no status** (doesn't help to know
whether the posting is open; see §3).

---

## 2. Search methodology (terms)

- **Multi-term + dedup by `id`.** Coverage varies A LOT: "segurança da informação" ≈138,
  "pentest" ≈4, "red team" ≈2, "segurança ofensiva" ≈1. Broad terms catch volume; specific ones
  catch precision. Use several and deduplicate.
- Current target terms (offensive security/AppSec, junior profile): `pentest`, `appsec`,
  `segurança da informação`, `red team`, `devsecops`, `segurança ofensiva`, `segurança cibernética`,
  `cyber security`.
- Accents matter in `jobName` (Gupy matches on the title text).

---

## 3. Project filters (recency + open) — client-side

The API doesn't filter by date/status; we do it client-side, in **cheap → expensive** order:

1. **Type** (`type ∈ {vacancy_type_effective, vacancy_type_internship}` by default — full-time + internship).
2. **Model** (`workplaceType ∈ {remote, hybrid}` — prioritize remote; no purely on-site).
3. **Recency:** discard `publishedDate` > **28 days** (there are jobs with 1900+ days listed!).
4. **Open:** see below. Only runs on the survivors (this is the expensive step: 1 GET per job).

### ⚠️ How to know whether the job is OPEN
- **`applicationDeadline` is USELESS:** it stays in the future even for an already-closed job (0/127
  in the past in the study). A job can be closed before the deadline ("staff_replacement" etc.).
- **Reliable signal = status on the career page.** The `jobUrl` is **Next.js SSR** and embeds:
  ```html
  <script id="__NEXT_DATA__" type="application/json">{ "props":{ "pageProps":{ "job":{
      "id":..., "status":"published" | "closed", ...
  }}}}</script>
  ```
  `status == "published"` → open; `"closed"` → closed. **Plain HTTP fetch** of the `jobUrl` +
  parse the JSON (no browser). See `_is_open()`. On error/failed parse → DO NOT discard (avoids
  losing a job over a transient).

Defaults and implementation: `discovery.py` (`DEFAULT_TYPES`, `DEFAULT_WORKPLACES`, `PAGE_LIMIT`,
`_is_recent`, `_is_open`, `_fetch_all`, `discover`).

### Discarding EXCLUSIVE AFFIRMATIVE-ACTION postings (immutable factor)
Applied by the orchestrator (`discover_rank.py`), not by the plugin's discovery — it's cross-platform
(`app/ai/eligibility.py`). An EXCLUSIVE affirmative-action posting (accepts only one group: PcD /
racial / gender) is **discarded** if the candidate doesn't belong to the group (`Profile.demographics()`:
pcd/race/gender). A cheap keyword pre-filter ("afirmativa", "talentos negros", "[pcd]"…) → only
suspects go to the AI (`deepseek-chat`), which distinguishes an **exclusive** posting from "the
company values diversity/benefit" (it doesn't discard those). `cleanup_jobs.py` also removes
affirmative-action postings already saved in the database.

---

## 4. Application (browser channel) — REAL flow

**Fixed across all of Gupy; what changes per company are the QUESTIONS** (answered by the AI, see §5).
Requires a logged-in session (`scripts/login.py gupy`). Engine: `run_auto_apply(page, ...)` in
`apply.py`, called by `scripts/auto_apply.py`. Step detection via `_detect_step()`.

### Sequence and selectors
| # | Step | How to detect | Action / button |
|---|---|---|---|
| 1 | **Start** (job page) | `a[data-testid="apply-link"]` | click "Candidatar-se" |
| 2 | **Resume review** | "advance" step (without the markers below) | **"Continuar"** button |
| 3 | **Additional data** | `input[name="radioGroupIsIndicatedTitle"]` | radios already default to "Não" (honest); optional source left blank; `button[name="saveAndContinueButton"]` **"Salvar e continuar"** |
| 4 | **"Company questions" landing** | `button[aria-label="Responder agora"]` | click "Responder agora" |
| 5 | **Company questions** | `.curriculum-content` with `textarea/input` | AI answers → fills → **"Salvar e continuar"** ⚠️ IRREVERSIBLE |
| 6 | **Modal** (`modal` step) | `#dialog-save-personalization-step` visible (overlays the form behind it) | **ALWAYS** "Personalizar candidatura" |
| 7 | **"Apresente-se"** | `#personalization-step-text-area` or `[data-testid="candidate-skill"]` | AI writes an introduction + picks ≤3 skills → **"Finalizar candidatura"** ⚠️ SUBMISSION |

> **Company WITHOUT questions (Cause G):** some jobs skip step 5 — after "data" (4) the "Salvar e
> continuar" opens the modal (6) DIRECTLY. That's why the modal is its **own step** in the loop
> (`_detect_step` → `kind="modal"`), not an inline click: it covers both paths (with and without
> company questions). The modal overlays the previous form in the DOM — detect it BEFORE data/company.

### Flow (`run_auto_apply` flowchart)

Engine = **LOOP**: `_detect_step(page)` classifies the current screen into a `kind`, the loop runs the
action and **detects again** (Gupy is an SPA — the URL barely changes between steps). The **detection
order** matters: `start → done → modal → personalize → respond_now → company → dados → advance` (the
modal overlays the form behind it; it must come before data/company).

```
  goto jobUrl (logged-in session)
        │
        ▼
  ┌──────────────────────────  LOOP  (up to max_steps)  ──────────────────────────┐
  │  _detect_step(page) → kind:                                                   │
  │                                                                               │
  │   start        → clicks "Candidatar-se" (a[data-testid=apply-link])  ─┐        │
  │   advance      → clicks "Continuar" (resume review)                  ─┤        │
  │   dados        → radios "Não" (REAL .click) → "Salvar e continuar"   ─┤        │
  │   respond_now  → clicks "Responder agora"                            ─┤ re-    │
  │   company      → AI answers+fills → "Salvar e continuar" ⚠️          ─┤ detects│
  │   modal        → "Personalizar candidatura" (#dialog-...)           ─┘        │
  │                                                                               │
  │   done         → RETURN already_applied ✅ (end)                             │
  │                                                                               │
  │   personalize  → AI: "Apresente-se" text + picks ≤3 skills                    │
  │                  → "Finalizar candidatura" ⚠️  SUBMISSION                     │
  │                  → _finalized_ok()?  ── yes → RETURN sent ✅ (end)            │
  │                                      └─ no  → RETURN error (retryable)         │
  │                                                                               │
  │   unknown[]/failure ≠ empty at the company step → RETURN needs_review (pause) │
  └───────────────────────────────────────────────────────────────────────────────┘

  Two paths to the modal:
    • WITH questions:  dados → respond_now → company →⚠️Salvar→ modal → personalize → Finalizar
    • WITHOUT questions:  dados ──────────────────────→⚠️Salvar→ modal → personalize → Finalizar

  ⚠️ = IRREVERSIBLE point: gated by allow_real (+ confirmation in the UI). Without allow_real = DRY-RUN
       (fills and stops). NEVER report sent without _finalized_ok (avoids false positive).
```

> Failure diagnosis (needs_review/incomplete/error/false positive): use the skill
> **`diagnose-gupy`** — 5-step method + Cause A–G catalog + dump snippets.

### Company questions details (step 5)
- Only the **FIRST** `div.curriculum-content` has the questions (extract with scope:
  `page.evaluate(EXTRACT_JS, ".curriculum-content")`).
- Each question = `<h3>N. Label *</h3>` (the `*` = required) + a field:
  - **textarea:** `id="input-<label>"`, `name="<label>"`, `maxlength=1000`.
  - **radio (MUI):** `input[name="question-<id>"]` with **`value=""`** (empty!) — match by the LABEL
    ("Sim"/"Não"/range), not by the value.
- Warning "**As respostas não poderão ser editadas depois.**" → that's why the "Salvar e continuar"
  here is gated as irreversible.

### Skills (step 7)
- Buttons `button[data-testid="candidate-skill"]`, each with a `<div>` = the skill name.
- Counter "N / 3 habilidades selecionadas" → **max. 3**. Clicking the button selects it.
- Extraction: `EXTRACT_JS` returns `snapshot.skills = {options, max}` → becomes `FormQuestion(kind="skills")`.

---

## 5. How the AI answers (form_agent) — summary

Philosophy: **answer ALL questions** (getting stuck on `unknown` makes mass automation unfeasible).
Full detail in `app/ai/form_agent.py`. Rules:
- Data in the PROFILE/EXTRAS → use it directly.
- **Availability/willingness/logistics** (Saturdays, shifts, travel, relocation, on-site) → what the
  company wants, almost always **"Sim"**.
- **Consent/LGPD/authorization** → **always "Sim"**.
- **Salary:** expectation = EXTRAS; **current/last = expectation − 8%**; range (radio) → the one that
  contains the value.
- **Factual/legal** (worked here before? family ties? PcD?) → **the truth from the profile**. Hard
  line: **never invent** a nonexistent tie/employment/seniority/certification.
- Free text ("apresente-se") → human voice (HUMANIZE), reusing the cover letter, in the job's language.

EXTRAS come from `Profile.to_application_extras()` (expectation, availability, PcD, source, free-form
FAQ), editable at `/profile`.

---

## 6. Safety / gating (DO NOT loosen)

- **Real submission** only with `ALLOW_REAL_SUBMIT=true` **or** the `--real` flag on `auto_apply.py`.
- `--real` submits **directly** (without asking); `--real --confirm` pauses at each irreversible step.
- **Irreversible points:** the "Salvar e continuar" of the company questions (locks the answers) and
  "Finalizar candidatura" (submission). Without `allow_real` → DRY-RUN: fills everything and **stops**
  before them.
- Each filled field and the result go to the `AuditLog` (`action="auto_apply"`).

---

## 7. Gotchas (traps already solved — don't regress)

- **⚠️ FALSE POSITIVE on finalization (critical, production):** NEVER report `sent` just because you
  clicked "Finalizar candidatura". Under **headless + concurrency (batch of 5)** the submit may not
  complete before the browser closes → the application ends up **started but NOT finalized** (a draft
  in the Gupy panel), and we used to report "sent" (false positive). A started-but-not-finalized
  application is a **FAILURE**. **Rule:** after clicking "Finalizar candidatura", **wait for the
  CONFIRMATION** — the screen turns into `heading "Candidatura finalizada!"` with "Acompanhar
  candidatura"/"Revisar meu currículo" buttons. Only then `sent`. See `_finalized_ok()` (waits for
  `"candidatura finalizada"`/"acompanhar candidatura" for ~20s); if it doesn't confirm → `error` (do
  NOT mark as sent, leave it retryable). Diagnosis: running **headed (1 browser)** the flow finalizes
  correctly; the problem shows up **headless/concurrent**.
- **Re-run on an already-finalized job:** `_detect_step` returns `done` (via `_DONE_MARKERS` in the
  text) → outcome `already_applied` (marks as sent, doesn't reprocess).
- **⚠️ AUTO-SAVED and DISABLED field (idempotency):** Gupy saves each answer and **disables the
  already-answered field**. On a re-run, `.fill()` on a `<textarea disabled>4000</textarea>` **hangs
  for 30s** and turns into `failed` → a false `needs_review`. **Rule** (`core/form_fill.apply_answers`):
  before filling text, check `is_editable()`; if NOT editable → already answered: OK if it has a value,
  fails only if empty; if editable → `fill(..., timeout=10000)` (never the default 30s).


- **Single-URL SPA:** the steps change without changing the URL (`.../steps/.../curriculum`). Don't
  rely on the URL to know the step; detect by selectors (`_detect_step`) and, when advancing, **wait
  for the step's SIGNATURE to change** (`_advance` compares `_sig` before/after) — Gupy saves async and
  the button stays **disabled** while saving (re-clicking gives a timeout).
- **The question's label** is in the `<h3>`/`<legend>`, not in the field. The extractor prioritizes
  the heading/legend of the nearest container (otherwise it would grab "Máx. 1000 caracteres" or the
  first option).
- **MUI radios** have `value=""` → match by the visible label, clicking the `<label>` (the input is
  hidden).
- **The "Salvar e continuar" button** only enables when all the required fields are filled in React's
  state — `.fill()` (textarea) and clicking the `<label>` (radio) fire the right events.

---

## 8. Known gaps (TODO)

- **⚠️ A per-job tailored CV is IMPOSSIBLE in the logged-in flow (Gupy restriction):** the application
  **always uses the PROFILE's CV** of the candidate — there is NO per-application upload. Confirmed by
  a DOM dump on a new job AND on one in progress: the resume step is just "Olá, vamos continuar sua
  candidatura?" + "Continuar", **without `input[type=file]`/dropzone** ("Meu currículo" is an account
  menu, not an upload). The tailored `cv_job_N.pdf` is for OTHER channels (email/LinkedIn/other
  platforms), not for Gupy. On Gupy, the tailored value comes from the **answers + personalization +
  skills** (which ARE already per-job). Alternative (heavy/risky): swap the PROFILE's CV before each
  submission — but it's global and re-parses the profile; not recommended.
- **Captcha** not yet triggered in the loop (use `core/captcha.py` if Gupy blocks).

---

## 9. Files

- `discovery.py` — search + filters (recency/open/type/model).
- `apply.py` — `run_auto_apply()` (browser flow) + `prepare()/submit()` (old queue flow).
- `manifest.py` — declarative (id/name/channel/endpoints/build).
- Shared core: `core/form_extract.py` (DOM→questions), `core/form_fill.py` (fill),
  `ai/form_agent.py` (answer), `core/browser.py` (Chromium CDP), `core/session.py` (session).
- Scripts: `scripts/login.py gupy`, `scripts/discover_rank.py gupy`, `scripts/tailor_job.py`,
  `scripts/auto_apply.py <id> [--real] [--confirm]`, `scripts/snapshot_form.py` (dev: DOM dump).

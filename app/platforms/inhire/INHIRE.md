# INHIRE — Plugin playbook (READ BEFORE TOUCHING)

> **Source of truth for the InHire methodology.** Consult before changing `discovery.py`,
> `apply.py` or `manifest.py`. Empirical findings (2026, live API + SPA bundle reverse-engineering) —
> revalidate if InHire changes. Complements `docs/PLATFORMS.md` and `CLAUDE.md`.
>
> Legend: ✅ confirmed empirically · 🔎 inferred, **to confirm in a supervised browser snapshot**.

Channel: **`api`** for discovery (anonymous HTTP, no captcha) + **`browser`** for the application
(the submit is gated by invisible reCAPTCHA v3 → must run in a real browser). Like Gupy, the plugin
**does not open a browser on its own** — it receives `page`/`session` from the harness.

InHire is **multi-tenant**: no global search; each company is a `tenant` (slug of `<slug>.inhire.app`).
Public endpoints require the header **`X-Tenant: <slug>`**. Target tenants live in a curated,
live-validated plugin list — **`tenants.py`** (`TENANTS`, ~96 companies, cyber-security first);
`INHIRE_TENANTS` in `.env` still works and **extends** it. There is no global search, so coverage =
the tenant list. Cyber examples: `tempest`, `clavis`, `asper`, `deloitte`, `kpmg`.

---

## 1. Job discovery (API channel, anonymous) ✅

**Host:** `https://api.inhire.app` · all calls send `X-Tenant: <slug>` (and `X-Inhire-Client: web-inhire`).

```
GET /job-posts/public/pages/lean          -> lean list (all jobs of the tenant; search is client-side)
GET /job-posts/public/pages/{jobId}       -> detail
GET /forms/public/job-id/{jobId}/subscription -> subscription form ref ({typeformId} or empty)
GET /tenants/public/resolve/{slug}        -> tenant metadata (XML)
```

- **lean item:** `jobId` (uuid), `displayName` (title), `link`, `careerPage`, `careerPageId`.
  Filtering by keyword is done on `displayName` in our code.
  - ⚠️ **The API's `link` is STALE:** it returns `https://<slug>.inhire.com.br/vagas/{jobId}`, but that
    domain **no longer resolves (dead DNS)**. The live career SPA is at
    **`https://<tenant>.inhire.app/vagas/{jobId}/{titleSlug}`** (confirmed 2026-07-10).
  - 🔴 **The `{titleSlug}` segment is REQUIRED.** A bare `/vagas/{jobId}` renders a **black screen** —
    the SPA never fetches the job (only the tenant config) and reCAPTCHA shows "não foi possível conectar".
    The slug is derived client-side from `displayName` (no slug field in the API): lowercase, strip
    accents (NFKD), non-alphanumeric → `-`, collapse/trim. `discovery.py::_slugify`/`_job_url` build it;
    e.g. "Analista de Segurança Ofensiva" → `.../vagas/{id}/analista-de-seguranca-ofensiva`. Do NOT use `link`.
- **detail fields:** `displayName`, `description` (HTML), `location`, `workplaceType` (`Remote`/`Hybrid`/`On-site`),
  `contractType` (`["CLT"]`…), `status`, `visibility`, `settings`, `activeJobBoards`, `privacyPolicyUrl`,
  `createdAt`, `publishedAt`, `lastPublishedAt`, `tenantName`.

### ⭐ Two detail fields that matter (InHire beats Gupy here)
- **`status`** — `"published"` = open. **Open/closed is known straight from the API** (no need to fetch
  the career page HTML, unlike Gupy's `__NEXT_DATA__` trick). Cheap open-filter.
- **`settings`** — **the application form spec, per job**:
  ```json
  {"fields": ["linkedin","salary","curriculum","workModel","referral","location"],
   "requiredFields": ["linkedin","salary","curriculum","workModel","location"]}
  ```
  `fields` = which standard fields the form shows; `requiredFields` = which are mandatory. The field
  set is a **fixed enum** (seen across tenants): `linkedin`, `salary`, `curriculum` (**CV upload**),
  `workModel`, `referral`, `location`, `cep`. Varies per job (some ask 3, some 6). `settings.email`
  (when present) is just the confirmation-email template, **not** a form field.

> **Discovery TODO (nice win):** use `status == "published"` as the open filter (API-level, 0 extra
> requests) instead of anything HTML-based. Also `settings` lets us know the exact fields BEFORE
> opening the browser — the apply step fills from it instead of guessing the DOM.

---

## 2. Application form spec (from `settings`) ✅

Per-job standard fields and what fills them (from `Profile`/`extras`, like Gupy):

| Field | Meaning | Source |
|---|---|---|
| `curriculum` | CV file upload (PDF) | `application.cv_pdf_path` (rendered — manifest `cv:"file"`) |
| `linkedin` | LinkedIn URL | `profile.linkedin_url` |
| `salary` | salary expectation | `extras` (expectation) |
| `workModel` | remote/hybrid/on-site preference | `extras`/profile pref |
| `location` | candidate location | `profile.location` |
| `cep` | postal code | `profile` (if present) |
| `referral` | referral source (optional) | blank/honest default |

Plus name/email/phone (the base candidate identity — the anonymous form always collects these). 🔎

**Custom questions = a Typeform.** `/forms/public/job-id/{jobId}/subscription` returns
`{typeformId, jobId, type:"subscription"}` when the job has extra questions. These are rendered as an
**embedded Typeform**, not a simple JSON field list — answering them programmatically is harder than
Gupy's inline questions. Many jobs have none. 🔎 Confirm per-job whether the Typeform blocks submit.

---

## 3. Application flow (browser channel) — architecture

**Submit endpoint:** `POST /job-talents/` (creates the talent→job link). ✅ (exact payload 🔎)
**Auth:** the SPA adds `Authorization: Bearer` **only if an accessToken exists** → public apply is
**ANONYMOUS** (no candidate login). ✅ **Differs from Gupy** (which requires a logged-in session).
**CV upload:** `POST /files/public/signature/` → presigned signature, then upload the file. ✅
**reCAPTCHA:** **v3 / Enterprise, invisible** (`grecaptcha.enterprise`, `badge:"inline"`,
`execute(sitekey,{action})`; sitekeys `6Lfq…`, `6Lfr…`). Header `X-Recaptcha` on the submit. ✅
→ **No checkbox to solve; a valid v3 token requires executing grecaptcha in a real browser.** This is
the decisive reason the apply is **browser-channel**, not a raw API POST.

### Why browser, not API
Replicating the submit out-of-browser would need: a valid reCAPTCHA v3 score token (browser-executed),
plus driving the Typeform for custom questions. Both fall out naturally when Playwright loads the real
career page. So `apply.py` implements `run_auto_apply(page, ...)` and drives the page — same pattern as
Gupy. The API layer is still used to KNOW the form (`settings`) and open status.

### ✅ Confirmed DOM (2026-07-10, automated capture — clavis "Analista de Segurança Ofensiva")
The apply form renders **inline** on `/vagas/{jobId}/{slug}` (no separate navigation needed — the whole
`<form data-component-name="JobForm" method="POST">` is already in the DOM once the SPA hydrates). It is a
**2-step wizard**: tab "1. Informações" → tab "2. Diversidade".

**Step 1 — Informações** (fill these, then click **Avançar**):
| DOM `name=` | Type | Label | Fills from |
|---|---|---|---|
| `name` | text | Nome completo * | profile name |
| `email` | email | Seu melhor email * | profile email |
| `phoneCountry` + `phone` | tel | Celular com DDD | profile phone |
| `linkedinUsername` | text | Linkedin * | `profile.linkedin_url` (`settings.fields: linkedin`) |
| `country` + `district` | text | Cidade * | `profile.location` (`location`) |
| `workModel` | radio Sim/Não | (remote pref) | `extras`/pref (`workModel`) |
| **`resume`** | **file, *req, hidden** | — | `application.cv_pdf_path` — click btn **"Anexar currículo"** then `set_input_files` (`curriculum`) |
| `salaryExpectation` | text | Pretensão salarial como CLT * | `extras` salary (`salary`) |
| `isIndication` | radio Não/Sim | (referral?) | honest default (`referral`) |

**Step 2 — Diversidade**:
| DOM `name=` | Type | Notes |
|---|---|---|
| `questionsDiversity.genderIdentity` | hidden/select | diversity self-ID (profile) |
| `questionsDiversity.peopleWithDisability` | hidden/select | diversity self-ID (profile) |
| `privacyPolicy` | checkbox, hidden, **required** | LGPD consent — must check to submit |
| `g-recaptcha-response` | hidden textarea | filled by grecaptcha v3 on submit (do not touch) |

**Buttons:** `"Candidatar"` / `"Candidatar-se para a vaga"` reveal/scroll to the form · `"Anexar currículo"`
opens the CV file picker · `"Avançar"` (disabled→enabled) advances step 1→2 · **`type=submit`
`"Continuar inscrição"`** (disabled→enabled) is the **IRREVERSIBLE submit** — gate on `allow_real`+`confirm()`.
Emotion CSS classes (`css-6134ia`…) are build-hashed → **select by text/`name`/`data-component-name`, not class.**

**No Typeform on this job** (`/forms/.../subscription` → the inline radios cover it; `questions:['Não']`).
Other jobs may still embed one — check `settings`/the subscription endpoint per job.

### Flow (legacy sketch — superseded by the confirmed DOM above)
```
  goto  https://<tenant>.inhire.com.br/vagas/{jobId}   (anonymous; stealth on — SPA blocks plain headless)
        │
        ▼
  click "Candidatar-se"/apply            🔎 selector
        │
        ▼
  fill the fields listed in settings.fields:
     name / email / phone                🔎
     linkedin, salary, workModel, location, cep  (only those in settings.fields)
     curriculum → upload application.cv_pdf_path  (set_input_files on the file input)  🔎
        │
        ▼
  if subscription typeform present → step through it (form_agent-style answers)  🔎
        │
        ▼
  reCAPTCHA v3 executes invisibly on submit  (no user action)
        │
        ▼
  ⚠️ SUBMIT (creates job-talent)  — gated by allow_real + confirm(); without it → DRY-RUN (fill & stop)
        │
        ▼
  wait for the CONFIRMATION screen/response before reporting `sent`   (avoid false positive, cf. Gupy)
```

---

## 4. Wiring notes (to resolve when implementing)
- **`has_session` gate:** `services.apply_application` blocks with `if not has_session("inhire")`.
  Apply is **anonymous**, so the gate must be skipped. **Decision (declarative):** the manifest now
  carries `anonymous_apply: True` — the harness/services check that flag instead of requiring a saved
  session. `scripts/snapshot_form.py` already honors it (opens the vaga anonymous + stealth, no gate).
  **PASSO 4 TODO:** make `services.apply_application` read `REGISTRY[platform].get("anonymous_apply")`
  and skip the `has_session` check when true. Do NOT require `scripts/login.py inhire`.
- **CV upload:** manifest is already `{cv:"file"}` → `application.cv_pdf_path` is rendered and ready.
- **Stealth:** plain headless Chromium does **not** render the SPA (anti-bot). Use the harness stealth
  (`core/stealth.py`) and/or headed; confirmed the page returns 200 but React never hydrates headless.
- **Idempotency / false positive:** mirror Gupy — only report `sent` after the confirmation response;
  a started-but-not-submitted apply is a FAILURE, not a success.

## 5. Open questions
1. ✅ **Exact DOM captured** — see §3 "Confirmed DOM". Apply CTA by text; CV file input = `input[name="resume"]`.
2. ✅ **Base identity always asked** (name/email/phone are inline step-1 fields). No email OTP seen on load.
3. ✅ **No Typeform on the sampled job** — custom questions are inline radios; the 2-step wizard covers it.
   (Still verify per job: a job with a subscription Typeform may add a step — handle when we hit one.)
4. ❌ **Confirmation signal after submit — STILL TO CAPTURE** (needs a real supervised dry-run/submit; we
   did NOT submit). Gate `sent` on the post-submit success screen, not on clicking "Continuar inscrição".
5. ❌ **Exact `POST /job-talents/` payload — STILL TO CAPTURE** (devtools during a supervised submit).

### 5.1 Automated-probe findings (2026-07-10, anonymous Chromium + stealth)
- ✅ **SPA loads anonymous** at `https://<tenant>.inhire.app/...`: shell hydrates
  (`main.5a7dd43c.js`, `InHire version 2026.395.0`), `#root` mounts `<main>`.
- ✅ **reCAPTCHA Enterprise invisible confirmed live** — iframe sitekey `6LfqLA4hAAAAAD5pmdD5SJiK3j7YatTCJi_02ktE`
  (`.../recaptcha/enterprise/anchor?...size=invisible`). Matches §3.
- ✅ Third-party widgets present: Hand Talk (a11y), UserGuiding, Intercom, GetDemo, Hotjar, Sentry.
- 🔴 **ROOT CAUSE of the black screen = missing title slug** (found via supervised test, user-confirmed):
  `/vagas/{jobId}` (no slug) → the SPA fetches only tenant config, **never `/job-posts/public/pages/{jobId}`**,
  reCAPTCHA errors ("não foi possível conectar"), `<main>` stays empty. Adding `/{titleSlug}` fixes it and
  the job renders. **Fixed in `discovery.py` (`_job_url`/`_slugify`).** The 429/503 seen earlier were a
  separate, self-inflicted rate-limit from repeated probes — real but secondary.
    - **Apply should still throttle** (human cadence + backoff on 429/503) — mirror the batch-cadence TODO.
- ❓ **Still to capture in the supervised snapshot** (now that the page renders): the apply-button selector,
  each field selector + the `curriculum` file input, the Typeform step (if any), and the post-submit
  confirmation signal. Re-run `snapshot_form.py` on a WITH-SLUG url and step through the form.

## 6. Files
- `discovery.py` — multi-tenant search (X-Tenant), keyword filter on `displayName`.
- `apply.py` — **stub today**; will hold `run_auto_apply()` (browser flow) once §5 is captured.
- `manifest.py` — declarative; `application: {cv:"file", cover_letter:True}`.
- Shared core to reuse: `core/form_extract.py`, `core/form_fill.py` (`set_cv_file`), `ai/form_agent.py`,
  `core/browser.py`, `core/stealth.py`. Dev tool (anonymous, stealth — no login needed):
  `scripts/snapshot_form.py --url https://<tenant>.inhire.com.br/vagas/<jobId> --platform inhire`
  (the manifest's `anonymous_apply` makes it skip the session gate; `--anon` forces it for any platform).

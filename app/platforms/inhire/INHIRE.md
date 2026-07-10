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

- **lean item:** `jobId` (uuid), `displayName` (title), `link` (`https://<slug>.inhire.com.br/vagas/{jobId}`),
  `careerPage`, `careerPageId`. Filtering by keyword is done on `displayName` in our code.
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

### Flow (🔎 selectors to be captured via supervised snapshot)
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
  Apply is **anonymous**, so either seed a dummy `PlatformSession` for inhire or relax that gate for
  anonymous-channel platforms. Do NOT require `scripts/login.py inhire`.
- **CV upload:** manifest is already `{cv:"file"}` → `application.cv_pdf_path` is rendered and ready.
- **Stealth:** plain headless Chromium does **not** render the SPA (anti-bot). Use the harness stealth
  (`core/stealth.py`) and/or headed; confirmed the page returns 200 but React never hydrates headless.
- **Idempotency / false positive:** mirror Gupy — only report `sent` after the confirmation response;
  a started-but-not-submitted apply is a FAILURE, not a success.

## 5. Open questions (capture in the supervised snapshot / dry-run)
1. Exact DOM: apply button, each field selector, the file input for `curriculum`.
2. Base identity fields (name/email/phone) — are they always asked? any email OTP/verification?
3. Typeform subscription: does it block submit? can `form_agent` answer it, or is it a separate flow?
4. Confirmation signal after submit (text/response) to gate `sent`.
5. Exact `POST /job-talents/` payload shape (capture via devtools during a real supervised apply).

## 6. Files
- `discovery.py` — multi-tenant search (X-Tenant), keyword filter on `displayName`.
- `apply.py` — **stub today**; will hold `run_auto_apply()` (browser flow) once §5 is captured.
- `manifest.py` — declarative; `application: {cv:"file", cover_letter:True}`.
- Shared core to reuse: `core/form_extract.py`, `core/form_fill.py` (`set_cv_file`), `ai/form_agent.py`,
  `core/browser.py`, `core/stealth.py`. Dev tool: `scripts/snapshot_form.py --url … --platform inhire`.

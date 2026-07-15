# SPEC — Application Assistant System

> Functional specification: the "what". Source of truth for the code (spec-first).
> Vision/"why" in `IDEA.md`. Architecture/"how" in `docs/ARCHITECTURE.md`.

## 1. Functional requirements (RF)

| ID | Requirement |
|---|---|
| RF-01 | Maintain a single user **Profile** (personal data, experience, skills, target roles, master CV). |
| RF-02 | **Import the master CV from LinkedIn's official data export** (ZIP/CSVs: Profile, Positions, Skills, Education, Certifications) → parse → `master_cv`; review/edit in the dashboard. No scraping (zero blocking risk). |
| RF-03 | **Discover jobs** in real time by target-role keywords, per enabled platform, **filtering by the seniority derived from `master_cv`** (e.g. junior/entry-level when there is no formal experience). |
| RF-04 | **Rank** each job (0–100 + rationale) by fit to the Profile. |
| RF-05 | **Generate a tailored CV + cover letter** per job, **in the language of the job description**. |
| RF-06 | **Render the CV/cover letter as a PDF** from a template. |
| RF-07 | **Fill the application** through the platform's channel (`api`/`browser`/`email`) and **stop before the final submission**. |
| RF-08 | **Human gate before submit**: each application requires the user's confirmation (confirm dialog) before the irreversible submit; manual mode fills and stops for review. |
| RF-09 | **Log** each submitted application (Application) and each relevant action (AuditLog). |
| RF-10 | **Manage sessions** per platform (manual login → `storage_state` saved and reused). |
| RF-11 | **Trigger captcha** (2Captcha) when the `browser` channel is blocked. |
| RF-12 | **Circuit breaker**: pause a plugin after N consecutive failures/captchas and flag it in the dashboard. |
| RF-13 | **Optional automatic mode** (toggle): submit without review, respecting filters (minimum score, platforms, cadence). |

## 2. Non-functional requirements (RNF)

| ID | Requirement |
|---|---|
| RNF-01 | **Local single-user** app; SQLite; no dependency on a hosted service. |
| RNF-02 | **Secrets out of git** (`.env`): `LLM_API_KEY`, `CAPTCHA_API_KEY`, SMTP. |
| RNF-03 | **Never store platform passwords** — only `storage_state` (session cookies). |
| RNF-04 | Plugins **do not open browser/HTTP on their own** — they receive `ctx`/`session` from the harness. |
| RNF-05 | AI outputs **validated against schema** before use. |
| RNF-06 | Each plugin testable **in isolation** via `apply_harness.py` (dry-run, without submitting). |
| RNF-07 | Configurable cadence/volume; "human" behavior (pauses, ordering) on the browser channel. |

## 3. Data models (SQLite / SQLModel)

> Indicative schema; type details may be adjusted during implementation.

**Profile** (single row in the MVP)
- `id`, `full_name`, `email`, `phone`, `location`, `linkedin_url`
- `summary` (professional summary), `experiences` (JSON), `skills` (JSON), `education` (JSON)
- `target_roles` (JSON: list of target roles + keywords), `languages` (JSON)
- `seniority` (`entry`/`junior`/`mid`/`senior`; **AI suggests it from `master_cv`, the user
  confirms/adjusts** in the dashboard; used to filter job discovery — see RF-03)
- `master_cv` (structured JSON, source for the tailor; **initial seed comes from
  `curriculum/curriculo.md`**), `created_at`, `updated_at`

**Job** (discovered job)
- `id`, `platform` (gupy/inhire/indeed/...), `external_id`, `url`
- `title`, `company`, `location`, `description`, `raw` (JSON of the original payload)
- `score` (0–100, nullable), `score_reason` (nullable)
- `status` (`discovered`/`ranked`/`tailored`/`pending_approval`/`applied`/`failed`)
- `hidden` (bool) — rejeitada/ocultada pelo usuário; filtrada de `/jobs` e `/queue`. A linha
  PERSISTE, então o dedupe por `(platform, external_id)` impede que a descoberta a reinsira.
- `discovered_at`

**Application** (application)
- `id`, `job_id` (FK), `cv_pdf_path`, `cover_letter_path`
- `cv_json` (generated JSON), `language` (language used)
- `submitted_at` (nullable), `result` (`sent`/`error`/`dry_run`), `error` (nullable)

**PlatformSession** (per-platform session)
- `id`, `platform`, `storage_state_path`, `valid` (bool), `last_login_at`

**AuditLog** (audit trail)
- `id`, `ts`, `platform`, `action` (`discover`/`rank`/`tailor`/`fill`/`submit`/`captcha`/`error`)
- `job_id` (nullable), `detail` (JSON)

## 4. Plugin contract (per channel)

Each plugin = an `app/platforms/<id>/` folder with:
- **`manifest.py`** — declarative: `id`, `name`, `channel` (`api`|`browser`|`email`),
  `base_url`/endpoints, expected `captcha`, an **`application`** block (what candidacy artifacts
  the platform consumes), lazy `build()`. Registered in `platforms/__init__.py`.
  - **`application` block** — `{"cv": "file"|"onplatform"|"none", "cover_letter": bool}`. It is the
    single declarative source that tells the harness which tailoring artifacts to produce, so
    `services.tailor_application` never hard-codes platform names. `cv`: **`file`** → render the CV
    PDF (the platform requires an uploaded/attached file, e.g. InHire); **`onplatform`** → generate
    only the structured content (`cv_json` + language), **no PDF** (the résumé lives in the platform's
    own builder, e.g. Gupy — the tailored content still feeds the form/screening answers, and a PDF
    upload is optional and skipped when absent); **`none`** → no tailoring at all. `cover_letter`
    controls whether the cover letter is generated/written. Adding a platform = fill these two fields,
    not a new pipeline.
- **`discovery.py`** — `discover(keywords, ctx_or_session) -> list[JobPosting]`
  (absent on the `email` channel).
- **`apply.py`** — `run_auto_apply(page, *, job, application, master_cv, extras, cover, allow_real,
  confirm, log_fn) -> dict` (browser channel): fills the form and submits. Irreversible steps only
  fire with `allow_real=True` **and** `confirm()`; otherwise it fills everything and stops for review.
  The harness owns the browser — the plugin never launches one. Discovery-only plugins may omit apply.

**Rules (validated by `check_contracts.py`):** a plugin does not call `chromium.launch`/`sync_playwright`,
does not import `web/`, uses the normalized schemas, and the `discover`/`apply` signature matches the channel.

## 5. AI output contracts (JSON, validated)

**Ranker** (`ai/ranker.py`)
```json
{ "score": 0-100, "reason": "string curta", "missing": ["requisito ausente", "..."] }
```

**Tailor** (`ai/tailor.py`)
```json
{
  "language": "pt|en|...",
  "cv": { "summary": "...", "skills": [...], "experiences": [...], "projects": [...],
          "education": [...], "certifications": [...] },
  "cover_letter": "texto da carta no idioma da vaga"
}
```
- CV **aggressively tailored to the job description**, **in ATS format** (see `ATS.md`) and with a
  **human voice not detectable as AI** (see `HUMANIZE.md`) — both mandatory: single column,
  canonical headings, mirrored keywords, skills matrix, bullets with metrics, varied sentence
  rhythm, no AI vocabulary/clichés, a 200–300 word cover letter with a real micro-episode.
- **Curated, not dumped.** The tailor reads the job and **selects** what reinforces it: it keeps the
  real jobs but rewrites/trims their bullets, and includes only the **1–3 most relevant projects**
  (dropping the rest), folding a headline metric (e.g. TryHackMe top 2%, standout badges) into the
  most relevant project or Achievements. Target length **1–2 pages**, ordered by relevance. Curation
  selects and rewrites real facts; it never fabricates.
- **Artifacts are per-platform (`manifest.application`).** Tailoring is two separable steps: **generate**
  the structured content (`cv_json` + cover, one LLM call) and **render** the file (PDF). The manifest's
  `application` block decides which run: a **`file`** platform (InHire) generates **and** renders the PDF;
  an **`onplatform`** platform (Gupy) generates the content but **skips the PDF** — the résumé is built in
  the platform and the content only backs the form answers. So `cv_pdf_path` may be empty for `onplatform`;
  the apply gate keys off generated content (`cv_json`), not the PDF.
- **Base = `Profile.master_cv`** (real and verifiable). The tailor **reframes and emphasizes** self-study,
  projects, and home labs as concrete experience, maximizing fit to the job — **without fabricating
  employment (company/role/dates) that never existed** (it falls apart in the technical interview and the
  background check). An experience gap is covered by a strong **Projects/Labs** section, not by an
  invented job.

**Form agent** (`ai/form_agent.py`, browser channel)
```json
{ "fields": [ { "selector_hint": "...", "label": "...", "value": "...", "type": "text|select|file|radio" } ],
  "unknown": ["labels que a IA não soube responder"] }
```

## 6. Dashboard endpoints (FastAPI + HTMX)

| Method | Route | Function |
|---|---|---|
| GET | `/` | Redirects to `/profile`. |
| GET/POST | `/profile` | View/edit Profile (contact, prefs, RG/CPF, FAQ). |
| POST | `/profile/suggest-seniority` | AI suggests seniority from the master CV. |
| GET | `/jobs` | List jobs (sorted by score). |
| POST | `/jobs/search` | Discover + rank (Gupy) — **background** (`bgtasks`), UI polls. |
| POST | `/jobs/tailor-all` | Batch-generate CV/cover (jobs ≥ min score) — **background** + polling. |
| GET | `/jobs/bg-status` | Poll a background task (`?task=search\|tailor`). |
| POST | `/jobs/{id}/tailor` | Generate CV/cover letter + PDF for the job. |
| GET | `/jobs/{id}/cv.pdf` | Download the tailored CV PDF. |
| GET | `/jobs/{id}/cover` | View the cover letter. |
| GET | `/jobs/{id}/questions` | View the AI's screening-form Q&A. |
| POST | `/jobs/{id}/apply` | Enqueue this job into the apply queue (headless, background). |
| POST | `/jobs/{id}/reject` | Reject/discard the job. |
| GET | `/queue` | Apply queue view + batch status. |
| POST | `/queue/apply-all` | Enqueue all prepared (CV generated, not sent) — max 5 browsers. |
| GET | `/queue/apply-status` | Poll the batch apply queue status. |

> Apply is fully automatic via the plugin's `run_auto_apply` (individual = enqueue 1, batch = enqueue N —
> same flow). The old manual `prepare`/`approve` routes were removed.

## 7. Flows per channel

> **Seniority filter in discovery:** every `discovery` applies the Profile's seniority level
> (RF-03) — e.g. it prioritizes junior/entry-level jobs when there is no formal experience,
> avoiding spending an application/AI on senior jobs out of reach. The `ranker` also penalizes
> a seniority mismatch.

- **API (Gupy/InHire):** `discovery` calls the public API → `JobPosting[]`. `apply` assembles the
  quick-application payload (CV in base64 + answers to the questions) → stops before the final
  POST in manual mode. **Gupy discovery confirmed:**
  `GET employability-portal.gupy.io/api/v1/jobs?jobName=<kw>&offset=&limit=` (no auth) — see
  `docs/PLATFORMS.md`.
- **Browser (Indeed/Catho/LinkedIn):** the harness opens a context with `storage_state` + stealth →
  `discovery` navigates the search → `apply` extracts `FormField[]`, `form_agent` maps the answers,
  Playwright fills them in and attaches the CV → stops before submit. Blocked → `captcha.py`.
- **Direct email:** no discovery; `apply` composes an email (CV attached + cover letter in the body) via SMTP.

## 8. Acceptance criteria per phase

- **Phase 1:** Profile imported from LinkedIn and editable; `ai/llm_client.py` returns valid JSON.
- **Phase 2:** `scripts/login.py` saves a session; `apply_harness.py` runs a sample plugin in dry-run.
- **Phase 3:** Gupy discovers real jobs and lists them in the dashboard; `apply` validates in dry-run.
- **Phase 4:** jobs displayed sorted by score with a rationale.
- **Phase 5:** CV/cover letter generated in the job's language and rendered as a PDF visible in the preview.
- **Phase 6 (vertical slice):** 1 real application on Gupy, reviewed and approved, logged in Application+AuditLog.
- **Phase 7:** at least +1 plugin per channel (browser, email) working; automatic-mode toggle with filters.

# SPEC — Application Assistant

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
| RF-08 | **Approval queue**: the user reviews and approves/rejects each application before submission. |
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
- `status` (`discovered`/`ranked`/`tailored`/`pending_approval`/`approved`/`applied`/`rejected`/`failed`)
- `discovered_at`

**Application** (application)
- `id`, `job_id` (FK), `cv_pdf_path`, `cover_letter_path`
- `cv_json` (generated JSON), `language` (language used)
- `submitted_at` (nullable), `result` (`sent`/`error`/`skipped`), `error` (nullable)

**PlatformSession** (per-platform session)
- `id`, `platform`, `storage_state_path`, `valid` (bool), `last_login_at`

**AuditLog** (audit trail)
- `id`, `ts`, `platform`, `action` (`discover`/`rank`/`tailor`/`fill`/`submit`/`captcha`/`error`)
- `job_id` (nullable), `detail` (JSON)

## 4. Plugin contract (per channel)

Each plugin = an `app/platforms/<id>/` folder with:
- **`manifest.py`** — declarative: `id`, `name`, `channel` (`api`|`browser`|`email`),
  `base_url`/endpoints, expected `captcha`, lazy `build()`. Registered in `platforms/__init__.py`.
- **`discovery.py`** — `discover(keywords, ctx_or_session) -> list[JobPosting]`
  (absent on the `email` channel).
- **`apply.py`** — `apply(job, application, ctx_or_session, *, dry_run) -> ApplyResult`.
  Stops before the final submission when in manual mode.

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
| GET | `/` | Dashboard (summary: jobs, approval queue, plugin status). |
| GET/POST | `/profile` | View/edit Profile; import-from-LinkedIn action. |
| POST | `/discover` | Trigger discovery (platforms + keywords). |
| GET | `/jobs` | List jobs (sorted by score), filters by status/platform. |
| POST | `/jobs/{id}/rank` | Rank (or re-rank) a job. |
| POST | `/jobs/{id}/tailor` | Generate CV/cover letter + PDF for the job. |
| GET | `/jobs/{id}/preview` | Preview the CV/cover letter (PDF). |
| POST | `/jobs/{id}/prepare` | Fill the application (dry-run → approval queue). |
| POST | `/jobs/{id}/approve` | Approve and submit. |
| POST | `/jobs/{id}/reject` | Reject/discard. |
| GET | `/sessions` | Per-platform session status. |
| GET | `/audit` | Audit trail. |

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

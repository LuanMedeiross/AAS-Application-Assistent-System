# Architecture — Application Assistant

> The "how". Technical decisions and structure. The "what" lives in `SPEC.md`; the "why" in
> IDEA.md. **When in doubt about an area, read its section here before touching it.**

## Core principle: shared harness + thin plugins

Inspired by `automation_launcher` (the user's project): a **core (harness)** handles everything
that is hard and shared — browser stealth, session, captcha, queue, circuit breaker,
HTTP/AI clients. Each **platform is a thin plugin** that only implements discovery + parsing
+ submit. The technical risk is concentrated and tested in the core; adding a platform = writing
a small plugin.

Each plugin declares a **channel**:
- `api` — uses the platform's public API (curl_cffi with TLS impersonation). No browser, no captcha. **Preferred.**
- `browser` — Chromium stealth via CDP + manual session. Captcha behind a lock.
- `email` — SMTP (application by direct email).

This mirrors `automation_launcher`'s `requests_mode` vs browser.

## Components

```
┌─────────────┐   ┌──────────────┐   ┌─────────────────────────┐
│  Dashboard  │──▶│   FastAPI    │──▶│  core/ (harness)        │
│ HTMX+Jinja2 │   │  routes.py   │   │  browser/session/captcha│
└─────────────┘   └──────┬───────┘   │  http_client/runner     │
                         │           └────────┬────────────────┘
                ┌────────▼────────┐           │
                │  ai/ (LLM)      │           ▼
                │ ranker/tailor/  │   ┌─────────────────┐   ┌──────────┐
                │ form_agent      │   │ platforms/<id>/ │──▶│ Gupy API │
                └────────┬────────┘   │ discovery+apply │   │ LinkedIn │
                         │            └─────────────────┘   │ Indeed…  │
                ┌────────▼────────┐                         └──────────┘
                │ db (SQLite)     │   ┌────────────┐
                │ Profile/Job/... │   │ pdf, email │
                └─────────────────┘   └────────────┘
```

## Folder structure

```
app/
  main.py            # cria o FastAPI, monta rotas, startup do harness
  config.py          # lê .env (LLM_API_KEY, CAPTCHA_API_KEY, SMTP_*)
  db.py              # engine SQLite + sessão SQLModel
  models.py          # Profile, Job, Application, PlatformSession, AuditLog
  applyqueue.py      # fila de candidatura em lote (ThreadPool, até 5 navegadores) + status p/ polling
  bgtasks.py         # tarefas longas single-shot (busca+ranqueio, CV em lote) fora da request HTTP

  core/              # HARNESS — não muda por plataforma
    browser.py       # ChromiumServer: 1 processo via CDP, connect_over_cdp, contextos isolados
    stealth.py       # get_stealth_script(): add_init_script (webdriver/languages/WebGL/timezone)
    session.py       # load/save storage_state por plataforma (data/sessions/<id>.json)
    http_client.py   # new_session(): curl_cffi impersonate="chrome", fallback requests
    captcha.py       # solve(type, sitekey, url): 2Captcha (turnstile/hcaptcha/recaptcha-v2)
    runner.py        # Applier base: filas (partial/errors/fatal), flag stop, circuit breaker
    schemas.py       # dataclasses: JobPosting, ApplicationForm, FormField, ApplyResult

  platforms/         # PLUGINS — 1 pasta por plataforma
    __init__.py      # REGISTRY: imports estáticos; registrar plugin novo aqui
    gupy/  inhire/  indeed/  catho/  linkedin/  email_direct/
      manifest.py    # declarativo: id/name/channel/endpoints/captcha + build()
      discovery.py   # discover(keywords, ctx|session) -> list[JobPosting]
      apply.py       # apply(job, application, ctx|session, dry_run) -> ApplyResult

  ai/
    llm_client.py    # client OpenAI-compatible (base_url/modelos do .env) + chamada JSON validada
    ranker.py        # score vaga x perfil (model_rank, default deepseek-chat)
    tailor.py        # CV + carta no idioma da vaga (model_generate, default deepseek-reasoner)
    form_agent.py    # FormField[] -> respostas (canal browser)

  pdf/render.py      # Jinja2 HTML (template ATS) -> PDF via Chromium (page.pdf)
  emailer/sender.py  # SMTP (canal email)
  web/               # routes.py + templates/ + static/

scripts/
  login.py           # login manual por plataforma -> salva storage_state
  apply_harness.py   # roda 1 plugin isolado, repo mockado, dry-run (espelha agent_harness.py)
  check_contracts.py # valida contrato dos plugins (regex; sem rede/DB)

data/                # app.db, sessions/, generated/ (PDFs)
curriculum/          # FONTE do master_cv: curriculo.pdf (export LinkedIn) + curriculo.md (legível)
```

> **`curriculum/`**: `curriculo.md` is the structured/readable version of the CV (faithful to
> `curriculo.pdf`). It is the base that populates `Profile.master_cv`. Update `.md` and `.pdf` together.

## Data flow (end to end)

1. **Discover** → `POST /jobs/search` runs the platform's `discovery.discover()` in the background
   (`bgtasks`) → writes `Job` (status `discovered`).
2. **Rank** → `ranker.score()` (same background task) → updates `Job.score`/`reason` (status `ranked`).
3. **Tailor** → `tailor.generate()` reads the description + Profile.master_cv → JSON resume/cover letter →
   `pdf.render()` generates the PDF (status `tailored`). Batch via `POST /jobs/tailor-all` (`bgtasks`).
4. **Apply** → `POST /jobs/{id}/apply` (individual) or `POST /queue/apply-all` (batch) enqueue into
   `applyqueue` → `services.apply_application()` opens the BrowserHarness (headless) and runs the
   plugin's `run_auto_apply()` (fills + submits, gated by the UI confirm dialog). An in-process claim
   (`_inflight`) prevents concurrent double-submit. On success → `Application.result=sent`,
   `Job.status=applied`, `AuditLog`. If the flow can't finish it stops at `needs_review` →
   `Job.status=pending_approval` (resume by re-triggering apply).

## Technical decisions and trade-offs

- **API-first**: where there is a public API (Gupy, InHire), we avoid the browser → more reliable, no
  captcha, faster. Trade-off: it depends on the stability of the undocumented API for some endpoints.
- **Single Chromium via CDP** (not 1 Playwright per thread): lower memory, isolated contexts.
  Ported from `automation_launcher/backend/browser.py`.
- **Stealth via `add_init_script`**: injects before `goto`. Spoofs `navigator.webdriver`,
  `languages`, WebGL, timezone. Reduces detection without promising invisibility.
- **Manual session (storage_state)**: we never store a password; the user logs in once. Trade-off:
  the session expires and requires occasional re-login.
- **AI via OpenAI-compatible API**: `LLM_BASE_URL`/`MODEL_RANK`/`MODEL_GENERATE` from `.env`
  (any OpenAI-compatible endpoint — DeepSeek by default, or a local server; defaults `deepseek-chat` for ranking, `deepseek-reasoner` for generation). Output forced to JSON and validated against `schemas`.
- **Circuit breaker**: N consecutive failures/captchas → `stop=True` + a signal on the dashboard. It does not burn
  the session or 2Captcha balance in a loop.
- **Human-in-the-loop by default**: `apply` stops before the final submission; automatic mode is opt-in.

## Session and captcha management

- `scripts/login.py <plataforma>` opens a headed Chromium; the user logs in; `session.py` saves
  `data/sessions/<id>.json`. `PlatformSession` records its validity.
- On the `browser` channel, the context is created with `storage_state=<id>.json` + stealth.
- If a challenge appears (Cloudflare Turnstile / hCaptcha / reCAPTCHA v2), `apply` calls
  `captcha.solve(...)` (2Captcha) and injects the token. Balance failure → fatal + pause.

## AI integration (reference)

```python
from openai import OpenAI
client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
# ranking: model=settings.model_rank (default deepseek-chat)
# geração: model=settings.model_generate (default deepseek-reasoner)
# response_format={"type": "json_object"}; validar contra schemas antes de usar
```

## What to port from `automation_launcher` (code reference)

| Here | Origin |
|---|---|
| `core/browser.py` | `backend/browser.py` (ChromiumServer, CDP) |
| `core/stealth.py` | `backend/utils.py` (`_STEALTH_SCRIPT`) |
| `core/http_client.py` | `backend/http_client.py` (curl_cffi impersonate) |
| `core/captcha.py` | `backend/captcha.py` (2Captcha) |
| `core/runner.py` | `backend/automation.py` (queues, stop, circuit breaker) |
| `scripts/apply_harness.py` | `scripts/agent_harness.py` (mocked repo, dry-run) |
| `scripts/check_contracts.py` | `scripts/check_contracts.py` (regex validation) |

> Adapt, don't blindly copy: the domain here is job/application, not legal-case lookup.

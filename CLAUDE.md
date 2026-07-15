# Application Assistant System

> **Project master context** (loaded in every session). App that automates job applications
> using an LLM (DeepSeek by default, or a local OpenAI-compatible server) + browser/API automation. Detail that is not a rule lives in
> `docs/` and is read on demand. **When in doubt about an area, open its doc BEFORE touching it.**

A **local single-user** app (Python, FastAPI + HTMX) that runs the
**discover → rank → adapt CV/cover letter → fill → submit** cycle for jobs, with human-in-the-loop.
Architecture: **shared harness (`core/`) + thin per-platform plugins (`platforms/`)**,
inspired by `automation_launcher`. Each plugin declares a **channel**: `api` | `browser` | `email`.

→ Vision/"why": **`IDEA.md`** · The "what": **`SPEC.md`** · The "how": **`docs/ARCHITECTURE.md`**
· UI and prompts: **`docs/DESIGN.md`** · **Resume rules: `ATS.md` + `HUMANIZE.md` (critical)**.

---

## Karpathy System (how to work)

An AI-assisted development methodology inspired by Andrej Karpathy. **Reduces the most common
LLM errors. Biases toward caution over speed.**

1. **Spec-first.** `SPEC.md`/`IDEA.md` are the source of truth. Code derives from the spec, not the
   other way around. Changed the behavior? Update the spec **before** or alongside.
2. **Small, incremental steps.** One vertical slice at a time, small reviewable diffs.
   Never a "big bang". If you wrote too much at once, break it up.
3. **AI on a tight leash** ("keep the AI on a tight leash"). Generate little code at a time, read
   it all before accepting. No large unverified outputs.
4. **Autonomy slider.** Start at low autonomy (review everything), raise the level only as
   confidence increases. Mirrors the app's own manual→automatic toggle.
5. **Concrete verification at every step.** Every increment has a real test/observation ("run it and
   see it working") before moving on. Explicit success criterion before coding.
6. **Lean context.** Focused, navigable prompts and docs, not long dumps.
7. **Human in command of irreversible decisions.** Submitting an application, spending tokens/2Captcha
   balance, touching external platforms → requires explicit approval.

---

## Inviolable rules (OVERRIDE any default)

1. **Plugins do not touch infrastructure.** A plugin (`platforms/<id>/`) **never** opens a browser
   (`chromium.launch`/`sync_playwright`) nor creates an HTTP session on its own — it receives `ctx`/`session`
   from the harness. Shared behavior goes in `core/`.
2. **Secrets out of git.** `LLM_API_KEY`, `CAPTCHA_API_KEY`, SMTP only in `.env` (gitignored).
   **Never** commit `.env`, `data/sessions/*`, nor `data/app.db`.
3. **Never store platform passwords.** Only `storage_state` (cookies), via manual login.
4. **Human-in-the-loop by default.** `apply` **stops before the final submission** in manual mode. Automatic
   mode is explicit opt-in.
5. **AI output always validated against `schemas.py`** before use. Never trust the raw JSON.
6. **All application text follows `ATS.md` + `HUMANIZE.md`** (ATS format + human voice not
   detectable as AI). Adapt aggressively to the job and honestly reframe self-study/projects/labs
   — **do not fabricate nonexistent employment**. When writing/reviewing any application
   text, use the skill **`write-application`**.
7. **Gate before touching a plugin:** `python scripts/check_contracts.py` must pass.

---

## Plugin contract (heart of the project)

Each platform = `app/platforms/<id>/` with:
- **`manifest.py`** — declarative: `id`, `name`, `channel`, `base_url`/endpoints, expected
  captcha, lazy `build()`. **Register in the registry** `platforms/__init__.py` (static imports).
- **`discovery.py`** — `discover(keywords, ctx|session) -> list[JobPosting]` (absent in the `email` channel).
- **`apply.py`** — `run_auto_apply(page, *, job, application, master_cv, extras, cover, allow_real,
  confirm, log_fn) -> dict` (browser channel): fills + submits; irreversible steps gated by
  `allow_real` + `confirm()`. Harness owns the browser. Discovery-only plugins may omit apply.

Normalized schemas (`JobPosting`, `ApplicationForm`, `FormField`, `ApplyResult`) in
`app/core/schemas.py`. → Full detail of the contract and channels: **`SPEC.md` §4** and
**`docs/ARCHITECTURE.md`**.

---

## Essential commands

| Command | For what |
|---|---|
| `pip install -r requirements.txt && playwright install chromium` | Setup. |
| `python scripts/login.py <plataforma>` | Manual login → saves session (`data/sessions/<id>.json`). |
| `uvicorn app.main:app --reload` | Runs the dashboard (dev). |
| `python scripts/apply_harness.py <id> --keywords "appsec" --dry-run` | Tests 1 plugin in isolation (does not submit). |
| `python scripts/check_contracts.py` | Plugin contract gate (no network/DB). |

---

## Stack

Python · FastAPI · Jinja2 + HTMX (no JS build) · SQLModel + SQLite · Playwright (CDP) ·
curl_cffi · PDF via Chromium (`page.pdf`) · AI via OpenAI-compatible API (SDK `openai`, `LLM_BASE_URL`/`MODEL_RANK`/`MODEL_GENERATE`
from `.env`; any OpenAI-compatible endpoint — DeepSeek by default, or a local server; defaults `deepseek-chat` for ranking, `deepseek-reasoner` for generation) · 2Captcha.

## Platform priority (by response rate / risk)

Gupy (API) → InHire (API) → Indeed (browser) → Catho (browser) → direct email → **LinkedIn
last** (aggressive anti-bot). Detail and data in `IDEA.md` / `SPEC.md`.

## Adding a platform / touching the core

- **New plugin:** create `platforms/<id>/` (3 files), register it in the registry, validate with
  `check_contracts.py` + `apply_harness.py` in dry-run before any real submission.
- **Change in `core/`:** affects all plugins — small step, verify with the harness.

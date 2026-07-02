# Application Assistant

A **local, single-user** app that automates job applications end to end using AI (OpenAI-compatible,
configurable via `.env` — defaults to DeepSeek) +
browser/API automation. It runs one loop — **discover → rank → tailor CV & cover letter → fill →
submit** — and keeps a human in the loop for anything irreversible.

Built as a **shared harness (`core/`) + thin per-platform plugins (`platforms/`)**: each plugin
declares a channel (`api` | `browser` | `email`), so adding a job board means writing three small
files, not touching the core.

## Features

- **Discover** open, recent postings on a platform by keyword.
- **Rank** each posting 0–100 against your profile with AI (weighted rubric).
- **Tailor** an ATS-friendly CV + cover letter per job, in the posting's language, rendered to PDF.
- **Apply** automatically: an AI agent fills the platform's screening form; irreversible steps stop
  for your approval (or run as a dry-run).
- **Dashboard** (FastAPI + HTMX): `/profile`, `/jobs` (search · rank · generate), `/queue` (apply
  one by one or in batches, up to 5 browsers).

## Platform support

| Platform | Channel | Status |
|---|---|---|
| **Gupy** | api + browser | ✅ Full loop (discover → rank → tailor → automatic apply) |
| **InHire** | api | 🟡 Discovery |
| Indeed / Catho | browser | ⬜ Planned |
| Direct email | email | ⬜ Planned |
| LinkedIn | browser | ⬜ Planned (last — aggressive anti-bot) |

> Documentation: `IDEA.md` (vision) · `SPEC.md` (the what) · `docs/ARCHITECTURE.md` (the how) ·
> `docs/DESIGN.md` (UI) · `ATS.md` (resume rules) · `CLAUDE.md` (guide + Karpathy System).

## License

[Apache-2.0](LICENSE). Provided **"AS IS", without warranty** (see sections 7–8 of the license).

## ⚠️ Responsible use (read before using)

This is a **local, single-user** tool for **personal use**. By using it, **you** are solely
responsible for how you operate it:

- **Respect the Terms of Service** of each platform (Gupy, InHire, Indeed, LinkedIn, etc.).
  Automation may violate the ToS and result in **your account being blocked** — the risk is yours.
- **Do not fabricate information.** The project is designed to honestly adapt real experiences and
  projects, **never** to invent employment, roles, seniority, or certifications (see `ATS.md`).
- **Your data is yours.** Your CV, credentials, and session cookies stay **on your machine only**
  (`.env`, `data/`, `curriculum/` are gitignored). Do not commit personal data.
- **Human review by default.** Real submission requires explicit approval; keep it that way until
  you fully trust the behavior.

The maintainers are not responsible for account blocks, misuse, or any damage arising from the
use of this tool.

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
copy .env.example .env   # fill in LLM_API_KEY (required); CAPTCHA_API_KEY / SMTP are optional
```

> PDF rendering uses Chromium (installed by Playwright). Only `LLM_API_KEY` is required to get
> started; captcha (2Captcha) and email (SMTP) are optional.

### Local / self-hosted model

The LLM calls go through the OpenAI SDK against a configurable endpoint, so any OpenAI-compatible
server works (Ollama, LM Studio, vLLM, LocalAI). Point `.env` at it — no code change needed:

```
LLM_BASE_URL=http://localhost:11434/v1   # Ollama (LM Studio: :1234/v1, vLLM: :8000/v1)
MODEL_GENERATE=qwen2.5:14b               # a capable model for CV/cover (14B+ recommended)
MODEL_RANK=qwen2.5:7b                    # ranking can use a smaller one
LLM_API_KEY=ollama                       # dummy, but must be non-empty
# LLM_JSON_MODE=off                      # set if your server rejects response_format=json_object
```

Note: small models follow the ATS/HUMANIZE rules and emit valid JSON less reliably, so expect more
`needs_review`.

## Populate the Profile

Your profile is the source of truth the AI uses to rank jobs and generate tailored CVs.

```powershell
# Option A — seed from a structured CV (copy the example, then edit it with your data):
copy curriculum\master_cv.example.json curriculum\master_cv.json
.\.venv\Scripts\python.exe scripts\seed_profile.py

# Option B — import from the official LinkedIn export (ZIP or directory of CSVs):
.\.venv\Scripts\python.exe scripts\import_linkedin.py "path\to\Basic_LinkedInDataExport.zip"
```

See `curriculum/README.md` for the profile format.

## Run the dashboard

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
# open http://127.0.0.1:8000/profile
```

Log in to a platform once to save its session, then drive the loop from the dashboard:

```powershell
.\.venv\Scripts\python.exe scripts\login.py gupy   # opens a browser for manual login → saves the session
```

## Command-line (optional)

The dashboard covers the full flow, but each step is also scriptable:

```powershell
.\.venv\Scripts\python.exe scripts\discover_rank.py gupy --keywords "appsec,pentest,red team"  # discover + rank
.\.venv\Scripts\python.exe scripts\tailor_job.py [job_id]                                        # generate CV + cover letter
.\.venv\Scripts\python.exe scripts\apply_harness.py gupy --keywords "appsec" --dry-run           # test a plugin in isolation
.\.venv\Scripts\python.exe scripts\check_contracts.py                                            # plugin contract gate
```

## Project status

Early but functional. The full loop works end to end on **Gupy** (discover → rank → tailored
CV/cover letter → automatic AI-driven application with human-in-the-loop, verified against real
postings). **InHire** discovery is in place; browser boards (Indeed/Catho/LinkedIn) and the email
channel are on the roadmap. This is a personal tool shared as-is — expect rough edges.

Contributions welcome, especially new platform plugins — see `docs/ARCHITECTURE.md` for the plugin
contract and `SPEC.md` §4 for the channel definitions.

# Application Assistant

Local app that automates job applications with AI (DeepSeek) + browser/API automation.
Cycle: **discover → rank → tailor CV/cover letter → fill → submit**, with human review.

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
# (Phase 2+) playwright install chromium
copy .env.example .env   # fill in DEEPSEEK_API_KEY, CAPTCHA_API_KEY, SMTP
```

> Note: Phase 1 uses only the lightweight subset (fastapi/uvicorn/sqlmodel/jinja2/openai). The
> other deps (playwright, curl_cffi, 2captcha) come in later phases. PDF is via Chromium.

## Populate the Profile

```powershell
# Option A — seed from the already-structured CV:
.\.venv\Scripts\python.exe scripts\seed_profile.py

# Option B — import from the official LinkedIn export (ZIP or directory of CSVs):
.\.venv\Scripts\python.exe scripts\import_linkedin.py "C:\caminho\Basic_LinkedInDataExport.zip"
```

## Run the dashboard

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
# open http://127.0.0.1:8000/profile
```

## Status

**Phase 1 complete** — FastAPI + HTMX skeleton, SQLite, models, seed of the master CV
(`curriculum/`), LinkedIn export parser, DeepSeek client + seniority suggestion, Profile
dashboard.

**Phase 2 complete** — Harness core (`app/core/`): single Chromium via CDP + stealth
(`browser.py`/`stealth.py`), reusable manual session (`session.py`), HTTP with TLS
impersonation (`http_client.py`), 2Captcha pipeline (`captcha.py`), base runner with circuit
breaker (`runner.py`). Scripts: `login.py` (manual login → session), `apply_harness.py`
(isolated smoke/dry-run), `check_contracts.py` (plugin gate).

```powershell
# test the browser harness:
.\.venv\Scripts\python.exe scripts\apply_harness.py gupy
# save a platform session (manual login):
.\.venv\Scripts\python.exe scripts\login.py gupy
```

**Phase 3 in progress** — Gupy plugin (`api` channel). **Discovery complete and verified** with
real data: `app/platforms/gupy/` (manifest + discovery) uses the public endpoint
`employability-portal.gupy.io/api/v1/jobs?jobName=`. Test:
```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe scripts\apply_harness.py gupy --keywords "appsec,pentest,red team"
```
Still missing the Gupy **apply** (requires the candidate's logged-in session — run
`scripts/login.py gupy`).

**Phase 4 (ranking) complete** — `ai/ranker.py` (DeepSeek `reasoner`, the strongest model)
scores each job 0–100 vs. the profile, penalizing seniority mismatch. Full flow in
`scripts/discover_rank.py` (discover → save to DB → rank) and the `/jobs` page in the dashboard
sorted by score.
```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe scripts\discover_rank.py gupy --keywords "appsec,pentest,red team"
# then open http://127.0.0.1:8000/jobs
```

**Phase 5 (generation + PDF) complete** — `ai/tailor.py` generates a tailored CV + cover letter
in the job's language (ATS + HUMANIZE + anti-fabrication, DeepSeek `reasoner`); `pdf/render.py`
renders the CV to PDF via Chromium. `scripts/tailor_job.py [job_id]` generates everything and
records the `Application`; the `/jobs` page shows the CV/cover letter and serves the PDF.
```powershell
.\.venv\Scripts\python.exe scripts\tailor_job.py        # uses the highest-scoring job
```

**Phase 6 (approval queue + apply) complete** — `/queue` in the dashboard with Prepare/Approve/
Reject; `platforms/gupy/apply.py` with a double lock (human approval + `ALLOW_REAL_SUBMIT` flag,
default `false` → dry-run); `core/audit.py` logs everything. Real submission is
**assisted/supervised** via `scripts/apply_job.py <job_id>` (opens the logged-in page for you to
finish). **Complete vertical slice:** discover → rank → generate CV/cover letter → review →
approve.

```powershell
.\.venv\Scripts\python.exe scripts\login.py gupy      # once: saves the session
# in .env: ALLOW_REAL_SUBMIT=true  (only when you actually submit, while supervising)
.\.venv\Scripts\python.exe scripts\apply_job.py 2     # assisted submission
```

**Phase 7 in progress** — **InHire** plugin (`api` channel, per company/tenant) built and
verified: `app/platforms/inhire/` uses `api.inhire.app/job-posts/public/pages/lean` with the
`X-Tenant` header. Configure the target companies in `INHIRE_TENANTS` in `.env`. Registered in
the registry (now: gupy, inhire).

The rest of Phase 7 (best built during real use, "apply and fix"): `browser`-channel plugins
(Indeed/Catho/LinkedIn — anti-bot, require login), `email` channel (SMTP), and the optional
automatic mode with filters.

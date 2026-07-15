# Idea — Application Assistant System

> Product vision and context. The "why" document. Technical decisions live in
> `docs/ARCHITECTURE.md`; the detailed "what" in `SPEC.md`.

## Problem

Applying for jobs is manual, repetitive, and slow work: searching for jobs across several
platforms, reading each description, adapting the resume, writing a cover letter, filling out the
form, and submitting. Anyone who does it well spends 20–40 min per job — and so ends up
sending generic applications or applying to only a few jobs.

Two market facts make this critical:
- **Speed wins**: applying within the **first 24h** of a job posting gives a **+64%** chance
  of an interview.
- **Personalization wins**: resumes tailored to the ATS and the description pass automatic
  filters more often (75% of CVs are blocked by ATS before a human sees them).

Doing both by hand, at scale, is impossible.

## Value proposition

An app that runs the **discover → rank → adapt → fill → submit** cycle end to
end, with AI (OpenAI-compatible, configurable via .env) handling the content and browser/API automation handling the
execution. The human stays in command of the important decisions (review and approve), not the
repetitive typing.

**Expected result:** apply to more jobs, faster, with a tailored CV/cover letter for
each one — without losing quality or control.

## Persona

An **offensive/defensive security** professional (red team, AppSec, security analyst)
looking for jobs in the field. Has a technical profile, understands automation, and is willing to run a
local tool that reuses their logged-in sessions. Wants broad coverage (BR + international
tech) without giving up well-crafted applications.

**Target roles (examples):** security analyst, red team, AppSec, pentester, security
engineer, security analyst.

## User flow (high level)

1. Define target roles and review the **master CV** (imported from LinkedIn) in the dashboard.
2. Log in manually once on the platforms (session saved and reused).
3. The app discovers jobs in real time on the enabled platforms.
4. AI **ranks** the jobs by fit to the profile.
5. For the chosen jobs, AI **generates a tailored CV + cover letter** (in the job's language).
6. The app **fills** the application (API or browser) and **stops before submitting**.
7. The user **reviews and approves** in the dashboard → the app submits and logs it.

## Scope (MVP)

- Initial platforms by priority: **Gupy** (API) → InHire (API) → Indeed/Catho
  (browser) → direct email → LinkedIn (last, aggressive anti-bot).
- Master CV imported from **LinkedIn's official data export** (ZIP/CSVs, no scraping);
  CV/cover letter generation in the **job's language** following `ATS.md`.
- Local dashboard (FastAPI + HTMX) for Profile, ranked jobs, preview, and the approval queue.
- **Manual** approval by default (human-in-the-loop).

## Out of scope (for now)

- Multi-user / hosted SaaS (the MVP is local, single-user, SQLite).
- Fully automatic mode without review (kept as an optional toggle, after the vertical slice).
- Interview tracking / application CRM beyond basic logging.
- Platforms outside the prioritized list.

## Risks and ToS (explicit awareness)

- Application automation **violates the terms** of some platforms; **LinkedIn** is the most
  aggressive (Cloudflare/reCAPTCHA, risk of account blocking). That is why it comes last and
  always via a manual session.
- **Mitigations:** the API channel where it exists (Gupy/InHire — no captcha), manual logged-in
  session (we do not store passwords), human-in-the-loop, a circuit breaker to stop at the first sign of
  blocking, and a captcha pipeline (2Captcha) triggered only when necessary.
- **Intended use:** the user's own real applications to their own jobs — not mass
  spam. Configurable volume and cadence to appear human.

## Why it will work

The architecture reuses a harness pattern already validated by the user (`automation_launcher`:
browser stealth + per-target plugins + isolated test harness). The technical risk of automation
is concentrated in a shared, tested core; each new platform is a thin plugin.

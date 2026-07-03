# Design — Application Assistant System

> Design of the dashboard and the AI prompts. Server-rendered UI (FastAPI + Jinja2 + HTMX),
> no JS build. State is communicated through color/form (chips, gauges), not decorative emoji.

## Design system

> Redesigned 2026-07-03. **Any frontend change: load the `artifact-design` skill first.** The
> system lives in `app/web/templates/base.html`.

- **Theme:** deliberate dark "operator" world (single-theme by choice — it's a local tooling app).
- **Tokens:** `--bg`/`--bg2`/`--panel`/`--panel2`/`--line`; text `--fg`/`--fg-dim`/`--muted`/`--faint`;
  brand/interactive `--accent`; **semantic (separate from accent)** `--ok` (enviada), `--warn`
  (revisar), `--err` (não avançou / erro), `--slate`.
- **Type:** `system-ui` for UI; `--mono` for numbers/score/platform tag (`tabular-nums`); uppercase
  `.eyebrow` micro-labels with letter-spacing.
- **Shell (every page):** sticky top bar — logo (dot + "Application Assistant System") + nav
  `Perfil · Vagas · Fila`, active tab highlighted from `request.url.path`. Content in a 920px column.

## Screens

### 1. Perfil (`/profile`)
Form: contact, "sobre mim" summary, target roles/keywords, skills + soft skills, application prefs
(salary, availability, RG/CPF, LGPD, FAQ), self-identification. "Import from LinkedIn" pre-fills the
fields for review (never saves without review). Note: `/` **redirects to `/profile`**.

### 2. Vagas (`/jobs`)
- **Command strip** (`.cmd`): search field + `Buscar`, and `CV em lote · score ≥ __` + `Gerar p/ todas`
  (controls share the same 40px height). Both run in **background** (`bgtasks`); the list updates via
  HTMX polling — no blocked request.
- **Funnel summary** (`.summary`): visíveis · **enviadas** (green) · **não avançou** (red) · **revisar**
  (amber) · CV pronto.
- **Job card** (`.job-card`):
  - score **gauge** (conic ring, colored by band: ≥75 green, ≥45 accent, else slate);
  - clickable **header** (title + `company · location · plat-tag`) opens the posting;
  - **state chip**: `enviada` / `não avançou` (red) / `revisar` / `erro` / `CV pronto` / `ranqueada`;
  - **actions**: `Gerar currículo` (no CV) or `Ver CV` / `Ver carta` / `Perguntas` / `Regerar` +
    **`Candidatar-se`** (when a CV exists and it's not sent);
  - **× reject** in the top-right → soft-hides the job (`hidden=True`; row persists, so discovery's
    `external_id` dedup never re-inserts it).

### 3. Fila (`/queue`)
Same card language. Top: `Candidatar em lote` + the live **queue-status panel** (`_batch_status.html`,
polls every 3s; queued/running/done with an icon per outcome). Lists jobs that already have a CV.

## Apply flow (unified)
`Candidatar-se` (individual, from `/jobs` or `/queue`) = enqueue **1** into `applyqueue`;
`Candidatar em lote` = enqueue **N**. **Same** headless background flow — the only difference is how
many jobs enter. An `hx-confirm` dialog is the human gate before the irreversible submit; progress
shows in the shared queue-status panel. An in-process claim prevents concurrent double-submit.

## AI prompt design

Principles: short instruction, **strict JSON output**, minimum necessary context, controlled
language. Always validate against `schemas.py`. Job description is sent **whole** (max context).

### Ranker (`model_rank`, default: deepseek-chat)
- **Input:** `target_roles` + `seniority` + Profile summary (skills/experience) +
  job title/description.
- **Task:** score the fit from 0–100, justify in 1–2 sentences, list missing requirements.
  **Penalize seniority mismatch** (e.g., a senior job for an entry-level profile).
- **Output:** `{ score, reason, missing[] }`. No text outside the JSON.

### Tailor (`model_generate`, default: deepseek-reasoner)
- **Input:** `Profile.master_cv` + job description + the rules in `ATS.md` + `HUMANIZE.md`.
- **Human voice (HUMANIZE.md):** varied rhythm (short + long sentences), a real specific detail
  per paragraph, a micro-episode in the cover letter, zero AI vocabulary/clichés, a 200–300 word cover letter.
- **Task:** (1) detect the job's language; (2) generate the resume **in ATS format** (see `ATS.md`),
  aggressively tailored to the description — keywords mirrored literally, skills matrix, bullets
  with metrics; (3) write a short cover letter in the same language.
- **Amplify competencies (do not fabricate facts):** highlight to the fullest the real skills/expertise the
  job asks for and emphasize self-study/projects/home labs as concrete experience; **do not fabricate
  an employment relationship, seniority, or certification** (see `ATS.md` — "Can vs. Cannot").
  Experience gap → a strong Projects/Labs section.
- **Output:** `{ language, cv{...}, cover_letter }`. Validate against `schemas.py` + the `ATS.md` checklist.

### Form agent (`model_generate`, default: deepseek-reasoner, browser channel)
- **Input:** `FormField[]` (label/type/options) + Profile + EXTRAS + job (whole description) + cover.
- **Philosophy:** it is **mandatory to answer every question** (avoid `unknown`); availability /
  logistics / consent lean toward what the company wants. `unknown` only when answering would mean
  lying about a verifiable credential, or for missing personal data (RG/CPF).
- **Output:** `{ answers[], unknown[] }`. Choices are validated against the options; low-confidence or
  invalid answers are flagged (`unknown` fields surface for review via `[Perguntas]`).

## UI error convention
- Session failure → banner "session expired, run `login.py <plataforma>`".
- Circuit breaker tripped → plugin marked as `pausado` with a reason.
- `unknown` field the form agent can't answer → the auto-apply flow **stops at `needs_review`**
  (never guesses); the user reviews via `[Perguntas]` and re-applies.
- Eliminated by a knockout question → the app records **`not_advanced`** (enviada mas reprovada),
  NOT an error.

# Design — Application Assistant

> Design of the dashboard and the AI prompts. Server-rendered UI (FastAPI + Jinja2 + HTMX),
> no JS build. No emojis/symbols in the UI unless requested — state is communicated through color/layout.

## Screens

### 1. Dashboard (`/`)
General overview and starting point. **Note:** `/` currently **redirects to `/profile`**; the nav is
Profile · Vagas · Fila. This summary dashboard is a planned view.
```
┌──────────────────────────────────────────────────────────────┐
│ Application Assistant                         [Profile] [Audit]│
├──────────────────────────────────────────────────────────────┤
│  Sessões:  Gupy [ok]   Indeed [expirada]   LinkedIn [—]       │
│                                                                │
│  Cargos-alvo: red team, appsec, security analyst   [Buscar]   │
│                                                                │
│  Fila de candidaturas (3)                                     │
│   • Pentester — Acme            score 88   [Candidatar-se]     │
│   • AppSec Eng — Beta           score 81   [Candidatar-se]     │
│   • Security Analyst — Gamma    score 74   [Candidatar-se]     │
│                                                                │
│  Últimas candidaturas: 12 enviadas · 2 erros                  │
└──────────────────────────────────────────────────────────────┘
```

### 2. Profile (`/profile`)
Edit data + import from LinkedIn.
```
┌──────────────────────────────────────────────────────────────┐
│ Profile                                  [Importar do LinkedIn]│
├──────────────────────────────────────────────────────────────┤
│ Nome [____]  Email [____]  Telefone [____]  Local [____]      │
│ Resumo profissional [__________________________________]      │
│ Experiências  [+ adicionar]                                   │
│   - Cargo / Empresa / período / descrição                     │
│ Skills [tag tag tag +]                                        │
│ Cargos-alvo (keywords) [tag tag +]                            │
│ Idiomas [pt, en]                                              │
│                                            [Salvar]           │
└──────────────────────────────────────────────────────────────┘
```
"Import from LinkedIn" opens/uses the manual session, extracts the data, and pre-fills the fields for the
user to review (it does not save automatically without review).

### 3. Ranked jobs (`/jobs`)
List ordered by score, with filters.
```
┌──────────────────────────────────────────────────────────────┐
│ Vagas   [Buscar ▸ background]   [Gerar CV em lote: score≥__]  │
├──────────────────────────────────────────────────────────────┤
│ 88  Pentester — Acme         Gupy    tailored [Ver CV][Regerar]│
│ 81  AppSec Eng — Beta        InHire  [Gerar currículo]         │
│ 74  Security Analyst — Gamma Indeed  tailored [Ver CV][Regerar]│
│ 60  SOC Analyst — Delta      Catho   ranked   [Gerar currículo]│
└──────────────────────────────────────────────────────────────┘
```
Búsca e geração em lote rodam em **background** (`bgtasks`) — a lista atualiza via polling HTMX.
Applying happens from the **queue** (§5), not here.

### 4. Generated CV/cover (inline)
`[Ver CV (PDF)]` (`/jobs/{id}/cv.pdf`) and `[Ver carta]` (`/jobs/{id}/cover`) show what the AI
produced. After an apply, `[Perguntas]` (`/jobs/{id}/questions`) shows the screening-form Q&A the
AI answered, for review.

### 5. Apply queue (`/queue`)
```
┌──────────────────────────────────────────────────────────────┐
│ Fila de candidaturas                    [Candidatar em lote]  │
├──────────────────────────────────────────────────────────────┤
│ 88 Pentester — Acme (Gupy) [Ver CV][Ver carta][Candidatar-se] │
│ ⏳ 2 na fila · 1 rodando · ✅ 3 enviada(s)      (polling 3s)    │
└──────────────────────────────────────────────────────────────┘
```
Apply is **automatic and headless**: `[Candidatar-se]` enqueues one job, `[Candidatar em lote]`
enqueues all prepared (CV generated, not sent) — **same flow**, max 5 browsers (`applyqueue`).
An `hx-confirm` dialog is the human gate before the irreversible submit; progress updates via polling.
After applying, `[Perguntas]` shows what the AI answered; `[Rejeitar]` discards a job.

## Navigation flow (HTMX)

- Actions (`Buscar`, `Gerar CV`, `Candidatar-se`, `Rejeitar`) are HTMX POSTs that **swap fragments**
  (the job row, the queue status card) without reloading the page.
- Long operations (discover/tailor) show a `processando` state in the fragment itself and
  update when they finish (HTMX polling or a direct response).
- State communicated through **color/typography**: `ok`/`enviada` (neutral-positive), `expirada`/`erro` (highlighted),
  `processando` (dimmed). No decorative icons.

## AI prompt design

Principles: short instruction, **strict JSON output**, minimum necessary context, controlled
language. Always validate against `schemas.py`.

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
- **Input:** `FormField[]` (label/type/options) + Profile + application data.
- **Task:** map each field to a value; mark as `unknown` anything it cannot answer
  confidently (instead of guessing).
- **Output:** `{ fields[], unknown[] }`. `unknown` fields are highlighted for the user during review.

## UI error convention
- Session failure → banner "session expired, run `login.py <plataforma>`".
- Circuit breaker tripped → plugin marked as `pausado` with a reason.
- `unknown` field the form agent can't answer → the auto-apply flow **stops at `needs_review`**
  (never guesses); the user reviews via `[Perguntas]` and re-applies.

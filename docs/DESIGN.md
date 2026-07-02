# Design — Application Assistant

> Design of the dashboard and the AI prompts. Server-rendered UI (FastAPI + Jinja2 + HTMX),
> no JS build. No emojis/symbols in the UI unless requested — state is communicated through color/layout.

## Screens

### 1. Dashboard (`/`)
General overview and starting point.
```
┌──────────────────────────────────────────────────────────────┐
│ Application Assistant                         [Profile] [Audit]│
├──────────────────────────────────────────────────────────────┤
│  Sessões:  Gupy [ok]   Indeed [expirada]   LinkedIn [—]       │
│                                                                │
│  Cargos-alvo: red team, appsec, security analyst   [Buscar]   │
│                                                                │
│  Fila de aprovação (3)                                         │
│   • Pentester — Acme            score 88   [Revisar]           │
│   • AppSec Eng — Beta           score 81   [Revisar]           │
│   • Security Analyst — Gamma    score 74   [Revisar]           │
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
│ Vagas    [plataforma ▾] [status ▾] [score min __]             │
├──────────────────────────────────────────────────────────────┤
│ 88  Pentester — Acme         Gupy    [Gerar CV] [Preparar]    │
│ 81  AppSec Eng — Beta        InHire  [Gerar CV] [Preparar]    │
│ 74  Security Analyst — Gamma Indeed  tailored   [Preparar]    │
│ 60  SOC Analyst — Delta      Catho   ranked     [Gerar CV]    │
└──────────────────────────────────────────────────────────────┘
```
Each row expands (HTMX) to show the description, the score justification, and missing requirements.

### 4. Resume/cover letter preview (`/jobs/{id}/preview`)
Shows the generated PDF + cover letter, side by side with the job posting description, before preparing.

### 5. Review application (approval queue)
```
┌──────────────────────────────────────────────────────────────┐
│ Revisar: Pentester — Acme (Gupy)                              │
├──────────────────────────────────────────────────────────────┤
│ [PDF do CV]        Respostas do formulário:                   │
│ [carta]             - Pretensão salarial: [____] (a revisar)  │
│                     - Disponibilidade: imediata               │
│                     - Pergunta X: <resposta IA>               │
│ Campos não resolvidos pela IA: 1   (destaque)                 │
│                          [Editar] [Aprovar e enviar] [Rejeitar]│
└──────────────────────────────────────────────────────────────┘
```

## Navigation flow (HTMX)

- Actions (`Buscar`, `Gerar CV`, `Preparar`, `Aprovar`) are HTMX POSTs that **swap fragments**
  (the job row, the queue card) without reloading the page.
- Long operations (discover/tailor) show a `processando` state in the fragment itself and
  update when they finish (HTMX polling or a direct response).
- State communicated through **color/typography**: `ok`/`enviada` (neutral-positive), `expirada`/`erro` (highlighted),
  `processando` (dimmed). No decorative icons.

## AI prompt design

Principles: short instruction, **strict JSON output**, minimum necessary context, controlled
language. Always validate against `schemas.py`.

### Ranker (`deepseek-reasoner`)
- **Input:** `target_roles` + `seniority` + Profile summary (skills/experience) +
  job title/description.
- **Task:** score the fit from 0–100, justify in 1–2 sentences, list missing requirements.
  **Penalize seniority mismatch** (e.g., a senior job for an entry-level profile).
- **Output:** `{ score, reason, missing[] }`. No text outside the JSON.

### Tailor (`deepseek-chat`)
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

### Form agent (`deepseek-chat`, browser channel)
- **Input:** `FormField[]` (label/type/options) + Profile + application data.
- **Task:** map each field to a value; mark as `unknown` anything it cannot answer
  confidently (instead of guessing).
- **Output:** `{ fields[], unknown[] }`. `unknown` fields are highlighted for the user during review.

## UI error convention
- Session failure → banner "session expired, run `login.py <plataforma>`".
- Circuit breaker tripped → plugin marked as `pausado` with a reason.
- `unknown` field from the form agent → blocks "Aprovar e enviar" until the user fills it in.

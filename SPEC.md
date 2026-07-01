# SPEC — Application Assistant

> Especificação funcional: o "o quê". Fonte da verdade para o código (spec-first).
> Visão/"por quê" em `ideia.md`. Arquitetura/"como" em `docs/arquitetura.md`.

## 1. Requisitos funcionais (RF)

| ID | Requisito |
|---|---|
| RF-01 | Manter um **Profile** único do usuário (dados pessoais, experiências, skills, cargos-alvo, CV-mestre). |
| RF-02 | **Importar CV-mestre do export oficial de dados do LinkedIn** (ZIP/CSVs: Profile, Positions, Skills, Education, Certifications) → parse → `master_cv`; revisão/edição no dashboard. Sem scraping (zero risco de bloqueio). |
| RF-03 | **Descobrir vagas** em tempo real por keywords dos cargos-alvo, por plataforma habilitada, **filtrando pela senioridade derivada do `master_cv`** (ex.: júnior/entry-level se não há experiência formal). |
| RF-04 | **Ranquear** cada vaga (0–100 + justificativa) por aderência ao Profile. |
| RF-05 | **Gerar CV + carta sob medida** por vaga, **no idioma da descrição** da vaga. |
| RF-06 | **Renderizar CV/carta em PDF** a partir de template. |
| RF-07 | **Preencher a candidatura** pelo canal da plataforma (`api`/`browser`/`email`) e **parar antes do envio final**. |
| RF-08 | **Fila de aprovação**: usuário revisa e aprova/rejeita cada candidatura antes do envio. |
| RF-09 | **Registrar** cada candidatura enviada (Application) e cada ação relevante (AuditLog). |
| RF-10 | **Gerenciar sessões** por plataforma (login manual → `storage_state` salvo e reutilizado). |
| RF-11 | **Acionar captcha** (2Captcha) quando o canal `browser` for bloqueado. |
| RF-12 | **Circuit breaker**: pausar um plugin após N falhas/captchas seguidos e sinalizar no dashboard. |
| RF-13 | **Modo automático opcional** (toggle): enviar sem revisão, respeitando filtros (score mínimo, plataformas, cadência). |

## 2. Requisitos não-funcionais (RNF)

| ID | Requisito |
|---|---|
| RNF-01 | App **local single-user**; SQLite; sem dependência de serviço hospedado. |
| RNF-02 | **Segredos fora do git** (`.env`): `DEEPSEEK_API_KEY`, `CAPTCHA_API_KEY`, SMTP. |
| RNF-03 | **Nunca armazenar senhas** de plataforma — só `storage_state` (cookies de sessão). |
| RNF-04 | Plugins **não abrem browser/HTTP sozinhos** — recebem `ctx`/`session` do harness. |
| RNF-05 | Saídas da IA **validadas contra schema** antes de uso. |
| RNF-06 | Cada plugin testável **isoladamente** via `apply_harness.py` (dry-run, sem enviar). |
| RNF-07 | Cadência/volume configuráveis; comportamento "humano" (pausas, ordem) no canal browser. |

## 3. Modelos de dados (SQLite / SQLModel)

> Schema indicativo; detalhes de tipos podem ajustar na implementação.

**Profile** (linha única no MVP)
- `id`, `full_name`, `email`, `phone`, `location`, `linkedin_url`
- `summary` (resumo profissional), `experiences` (JSON), `skills` (JSON), `education` (JSON)
- `target_roles` (JSON: lista de cargos-alvo + keywords), `languages` (JSON)
- `seniority` (`entry`/`junior`/`mid`/`senior`; **IA sugere a partir do `master_cv`, usuário
  confirma/ajusta** no dashboard; usado para filtrar a descoberta de vagas — ver RF-03)
- `master_cv` (JSON estruturado, fonte para o tailor; **seed inicial vem de
  `curriculum/curriculo.md`**), `created_at`, `updated_at`

**Job** (vaga descoberta)
- `id`, `platform` (gupy/inhire/indeed/...), `external_id`, `url`
- `title`, `company`, `location`, `description`, `raw` (JSON do payload original)
- `score` (0–100, nullable), `score_reason` (nullable)
- `status` (`discovered`/`ranked`/`tailored`/`pending_approval`/`approved`/`applied`/`rejected`/`failed`)
- `discovered_at`

**Application** (candidatura)
- `id`, `job_id` (FK), `cv_pdf_path`, `cover_letter_path`
- `cv_json` (JSON gerado), `language` (idioma usado)
- `submitted_at` (nullable), `result` (`sent`/`error`/`skipped`), `error` (nullable)

**PlatformSession** (sessão por plataforma)
- `id`, `platform`, `storage_state_path`, `valid` (bool), `last_login_at`

**AuditLog** (trilha de auditoria)
- `id`, `ts`, `platform`, `action` (`discover`/`rank`/`tailor`/`fill`/`submit`/`captcha`/`error`)
- `job_id` (nullable), `detail` (JSON)

## 4. Contrato dos plugins (por canal)

Cada plugin = pasta `app/platforms/<id>/` com:
- **`manifest.py`** — declarativo: `id`, `name`, `channel` (`api`|`browser`|`email`),
  `base_url`/endpoints, `captcha` esperado, `build()` lazy. Registrado em `platforms/__init__.py`.
- **`discovery.py`** — `discover(keywords, ctx_or_session) -> list[JobPosting]`
  (ausente no canal `email`).
- **`apply.py`** — `apply(job, application, ctx_or_session, *, dry_run) -> ApplyResult`.
  Para antes do envio final quando em modo manual.

**Regras (validadas por `check_contracts.py`):** plugin não chama `chromium.launch`/`sync_playwright`,
não importa `web/`, usa os schemas normalizados, e a assinatura de `discover`/`apply` casa com o canal.

## 5. Contratos de saída da IA (JSON, validados)

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
- CV **adaptado agressivamente à descrição da vaga**, **no formato ATS** (ver `ATS.md`) e com
  **voz humana não detectável como IA** (ver `HUMANIZE.md`) — ambos obrigatórios: coluna única,
  headings canônicos, keywords espelhadas, skills matrix, bullets com métrica, ritmo de frase
  variado, sem vocabulário/clichês de IA, carta de 200–300 palavras com micro-episódio real.
- **Base = `Profile.master_cv`** (real e verificável). O tailor **reframe e enfatiza** autoestudo,
  projetos e home labs como experiência concreta, maximizando aderência à vaga — **sem fabricar
  vínculo empregatício (empresa/cargo/datas) que não existiu** (quebra na entrevista técnica e no
  background check). Lacuna de experiência é coberta por seção **Projetos/Labs** forte, não por
  emprego inventado.

**Form agent** (`ai/form_agent.py`, canal browser)
```json
{ "fields": [ { "selector_hint": "...", "label": "...", "value": "...", "type": "text|select|file|radio" } ],
  "unknown": ["labels que a IA não soube responder"] }
```

## 6. Endpoints do dashboard (FastAPI + HTMX)

| Método | Rota | Função |
|---|---|---|
| GET | `/` | Dashboard (resumo: vagas, fila de aprovação, status dos plugins). |
| GET/POST | `/profile` | Ver/editar Profile; ação de importar do LinkedIn. |
| POST | `/discover` | Disparar descoberta (plataformas + keywords). |
| GET | `/jobs` | Listar vagas (ordenadas por score), filtros por status/plataforma. |
| POST | `/jobs/{id}/rank` | Ranquear (ou re-ranquear) uma vaga. |
| POST | `/jobs/{id}/tailor` | Gerar CV/carta + PDF para a vaga. |
| GET | `/jobs/{id}/preview` | Preview do CV/carta (PDF). |
| POST | `/jobs/{id}/prepare` | Preencher candidatura (dry-run → fila de aprovação). |
| POST | `/jobs/{id}/approve` | Aprovar e enviar. |
| POST | `/jobs/{id}/reject` | Rejeitar/descartar. |
| GET | `/sessions` | Status das sessões por plataforma. |
| GET | `/audit` | Trilha de auditoria. |

## 7. Fluxos por canal

> **Filtro de senioridade na descoberta:** toda `discovery` aplica o nível de senioridade do
> Profile (RF-03) — ex.: prioriza vagas júnior/entry-level quando não há experiência formal,
> evitando gastar candidatura/IA em vagas sênior fora de alcance. O `ranker` também penaliza
> descompasso de senioridade.

- **API (Gupy/InHire):** `discovery` chama a API pública → `JobPosting[]`. `apply` monta o
  payload de candidatura rápida (CV em base64 + respostas das perguntas) → para antes do POST
  final em modo manual. **Gupy discovery confirmado:**
  `GET employability-portal.gupy.io/api/v1/jobs?jobName=<kw>&offset=&limit=` (sem auth) — ver
  `docs/plataformas.md`.
- **Browser (Indeed/Catho/LinkedIn):** harness abre contexto com `storage_state` + stealth →
  `discovery` navega busca → `apply` extrai `FormField[]`, `form_agent` mapeia respostas,
  Playwright preenche e anexa CV → para antes do submit. Bloqueio → `captcha.py`.
- **Email direto:** sem discovery; `apply` monta email (CV anexo + carta no corpo) via SMTP.

## 8. Critérios de aceite por fase

- **Fase 1:** Profile importado do LinkedIn e editável; `ai/deepseek.py` retorna JSON válido.
- **Fase 2:** `scripts/login.py` salva sessão; `apply_harness.py` roda um plugin de exemplo em dry-run.
- **Fase 3:** Gupy descobre vagas reais e lista no dashboard; `apply` valida em dry-run.
- **Fase 4:** vagas exibidas ordenadas por score com justificativa.
- **Fase 5:** CV/carta gerados no idioma da vaga e renderizados em PDF visível no preview.
- **Fase 6 (fatia vertical):** 1 candidatura real na Gupy, revisada e aprovada, registrada em Application+AuditLog.
- **Fase 7:** ao menos +1 plugin por canal (browser, email) funcionando; toggle de modo automático com filtros.

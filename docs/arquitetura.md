# Arquitetura — Application Assistant

> O "como". Decisões técnicas e estrutura. O "o quê" está em `SPEC.md`; o "por quê" em
> `ideia.md`. **Em dúvida sobre uma área, leia a seção dela aqui antes de mexer.**

## Princípio central: harness compartilhado + plugins finos

Inspirado no `automation_launcher` (projeto do usuário): um **núcleo (harness)** cuida de tudo
que é difícil e compartilhado — browser stealth, sessão, captcha, fila, circuit breaker,
clientes HTTP/IA. Cada **plataforma é um plugin fino** que só implementa descoberta + parsing
+ submit. O risco técnico fica concentrado e testado no núcleo; adicionar plataforma = escrever
um plugin pequeno.

Cada plugin declara um **canal**:
- `api` — usa a API pública da plataforma (curl_cffi com TLS impersonation). Sem navegador, sem captcha. **Preferido.**
- `browser` — Chromium stealth via CDP + sessão manual. Captcha sob bloqueio.
- `email` — SMTP (candidatura por email direto).

Isso espelha o `requests_mode` vs browser do `automation_launcher`.

## Componentes

```
┌─────────────┐   ┌──────────────┐   ┌─────────────────────────┐
│  Dashboard  │──▶│   FastAPI    │──▶│  core/ (harness)        │
│ HTMX+Jinja2 │   │  routes.py   │   │  browser/session/captcha│
└─────────────┘   └──────┬───────┘   │  http_client/runner     │
                         │           └────────┬────────────────┘
                ┌────────▼────────┐           │
                │  ai/ (DeepSeek) │           ▼
                │ ranker/tailor/  │   ┌─────────────────┐   ┌──────────┐
                │ form_agent      │   │ platforms/<id>/ │──▶│ Gupy API │
                └────────┬────────┘   │ discovery+apply │   │ LinkedIn │
                         │            └─────────────────┘   │ Indeed…  │
                ┌────────▼────────┐                         └──────────┘
                │ db (SQLite)     │   ┌────────────┐
                │ Profile/Job/... │   │ pdf, email │
                └─────────────────┘   └────────────┘
```

## Estrutura de pastas

```
app/
  main.py            # cria o FastAPI, monta rotas, startup do harness
  config.py          # lê .env (DEEPSEEK_API_KEY, CAPTCHA_API_KEY, SMTP_*)
  db.py              # engine SQLite + sessão SQLModel
  models.py          # Profile, Job, Application, PlatformSession, AuditLog

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
    deepseek.py      # client openai(base_url=api.deepseek.com) + chamada JSON validada
    ranker.py        # score vaga x perfil (deepseek-reasoner)
    tailor.py        # CV + carta no idioma da vaga (deepseek-chat)
    form_agent.py    # FormField[] -> respostas (canal browser)

  pdf/render.py      # Jinja2 HTML -> WeasyPrint PDF
  emailer/sender.py  # SMTP (canal email)
  web/               # routes.py + templates/ + static/

scripts/
  login.py           # login manual por plataforma -> salva storage_state
  apply_harness.py   # roda 1 plugin isolado, repo mockado, dry-run (espelha agent_harness.py)
  check_contracts.py # valida contrato dos plugins (regex; sem rede/DB)

data/                # app.db, sessions/, generated/ (PDFs)
curriculum/          # FONTE do master_cv: curriculo.pdf (export LinkedIn) + curriculo.md (legível)
```

> **`curriculum/`**: o `curriculo.md` é a versão estruturada/legível do CV (fiel ao
> `curriculo.pdf`). É a base que popula `Profile.master_cv`. Atualizar `.md` e `.pdf` juntos.

## Fluxo de dados (ponta a ponta)

1. **Discover** → `routes /discover` chama `discovery.discover()` de cada plugin habilitado →
   grava `Job` (status `discovered`).
2. **Rank** → `ranker.score()` → atualiza `Job.score`/`reason` (status `ranked`).
3. **Tailor** → `tailor.generate()` lê descrição + Profile.master_cv → JSON CV/carta →
   `pdf.render()` gera PDF (status `tailored`).
4. **Prepare** → `apply.apply(dry_run=True)` monta payload/preenche form sem enviar →
   `Application` em `pending_approval`.
5. **Approve** → `apply.apply(dry_run=False)` envia → `Application.result=sent`, `Job.status=applied`,
   `AuditLog`.

## Decisões técnicas e trade-offs

- **API-first**: onde há API pública (Gupy, InHire), evitamos navegador → mais confiável, sem
  captcha, mais rápido. Trade-off: depende da estabilidade da API não-documentada para alguns endpoints.
- **Chromium único via CDP** (não 1 Playwright por thread): memória menor, contextos isolados.
  Portado do `automation_launcher/backend/browser.py`.
- **Stealth via `add_init_script`**: injeta antes do `goto`. Spoofa `navigator.webdriver`,
  `languages`, WebGL, timezone. Reduz detecção sem prometer invisibilidade.
- **Sessão manual (storage_state)**: nunca guardamos senha; usuário loga uma vez. Trade-off:
  sessão expira e exige re-login ocasional.
- **DeepSeek via SDK `openai`**: `base_url=https://api.deepseek.com`. `deepseek-reasoner` para
  ranking (decisão), `deepseek-chat` para geração. Saída forçada a JSON e validada contra `schemas`.
- **Circuit breaker**: N falhas/captcha seguidos → `stop=True` + sinal no dashboard. Não queima
  sessão nem saldo 2Captcha em loop.
- **Human-in-the-loop padrão**: `apply` para antes do envio final; modo automático é opt-in.

## Gestão de sessão e captcha

- `scripts/login.py <plataforma>` abre Chromium headed; usuário loga; `session.py` salva
  `data/sessions/<id>.json`. `PlatformSession` registra validade.
- No canal `browser`, o contexto é criado com `storage_state=<id>.json` + stealth.
- Se aparecer challenge (Cloudflare Turnstile / hCaptcha / reCAPTCHA v2), `apply` chama
  `captcha.solve(...)` (2Captcha) e injeta o token. Falha de saldo → fatal + pausa.

## Integração DeepSeek (referência)

```python
from openai import OpenAI
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
# ranking: model="deepseek-reasoner"; geração: model="deepseek-chat"
# response_format={"type": "json_object"}; validar contra schemas antes de usar
```

## O que portar do `automation_launcher` (referência de código)

| Aqui | Origem |
|---|---|
| `core/browser.py` | `backend/browser.py` (ChromiumServer, CDP) |
| `core/stealth.py` | `backend/utils.py` (`_STEALTH_SCRIPT`) |
| `core/http_client.py` | `backend/http_client.py` (curl_cffi impersonate) |
| `core/captcha.py` | `backend/captcha.py` (2Captcha) |
| `core/runner.py` | `backend/automation.py` (filas, stop, circuit breaker) |
| `scripts/apply_harness.py` | `scripts/agent_harness.py` (repo mockado, dry-run) |
| `scripts/check_contracts.py` | `scripts/check_contracts.py` (validação por regex) |

> Adaptar, não copiar cego: o domínio aqui é vaga/candidatura, não consulta processual.

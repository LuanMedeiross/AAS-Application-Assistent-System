# Application Assistant

> **Contexto-mestre do projeto** (carregado em toda sessão). App que automatiza candidatura a
> vagas usando DeepSeek (IA) + automação de navegador/API. Detalhe que não é regra mora em
> `docs/` e é lido sob demanda. **Em dúvida sobre uma área, abra o doc dela ANTES de mexer.**

App **local single-user** (Python, FastAPI + HTMX) que executa o ciclo
**descobrir → ranquear → adaptar CV/carta → preencher → enviar** vagas, com human-in-the-loop.
Arquitetura: **harness compartilhado (`core/`) + plugins finos por plataforma (`platforms/`)**,
inspirada no `automation_launcher`. Cada plugin declara um **canal**: `api` | `browser` | `email`.

→ Visão/"por quê": **`ideia.md`** · O "o quê": **`SPEC.md`** · O "como": **`docs/arquitetura.md`**
· UI e prompts: **`docs/design.md`** · **Regras de currículo: `ATS.md` + `HUMANIZE.md` (críticos)**.

---

## Sistema Karpathy (como trabalhar)

Metodologia de desenvolvimento com IA inspirada em Andrej Karpathy. **Reduz os erros mais comuns
de LLM. Enviesa para cautela sobre velocidade.**

1. **Spec-first.** `SPEC.md`/`ideia.md` são a fonte da verdade. O código deriva da spec, não o
   contrário. Mudou o comportamento? Atualize a spec **antes** ou junto.
2. **Passos pequenos e incrementais.** Uma fatia vertical por vez, diffs pequenos e revisáveis.
   Nunca um "big bang". Se escreveu muito de uma vez, quebre.
3. **IA na coleira curta** ("keep the AI on a tight leash"). Gere pouco código por vez, leia
   tudo antes de aceitar. Nada de grandes saídas não verificadas.
4. **Autonomy slider.** Comece em baixa autonomia (revisar tudo), suba o nível só conforme a
   confiança aumenta. Espelha o toggle manual→automático do próprio app.
5. **Verificação concreta a cada passo.** Todo incremento tem um teste/observação real ("rodar e
   ver funcionando") antes de seguir. Critério de sucesso explícito antes de codar.
6. **Contexto enxuto.** Prompts e docs focados e navegáveis, não despejos longos.
7. **Humano no comando das decisões irreversíveis.** Enviar candidatura, gastar tokens/saldo
   2Captcha, tocar plataformas externas → exige aprovação explícita.

---

## Regras invioláveis (OVERRIDE qualquer default)

1. **Plugins não tocam infraestrutura.** Um plugin (`platforms/<id>/`) **nunca** abre browser
   (`chromium.launch`/`sync_playwright`) nem cria sessão HTTP sozinho — recebe `ctx`/`session`
   do harness. Comportamento compartilhado vai em `core/`.
2. **Segredos fora do git.** `DEEPSEEK_API_KEY`, `CAPTCHA_API_KEY`, SMTP só no `.env` (gitignored).
   **Nunca** commitar `.env`, `data/sessions/*`, nem `data/app.db`.
3. **Nunca armazenar senhas de plataforma.** Só `storage_state` (cookies), via login manual.
4. **Human-in-the-loop por padrão.** `apply` **para antes do envio final** em modo manual. Modo
   automático é opt-in explícito.
5. **Saída de IA sempre validada contra `schemas.py`** antes de uso. Nada de confiar no JSON cru.
6. **Todo texto de candidatura segue `ATS.md` + `HUMANIZE.md`** (formato ATS + voz humana não
   detectável como IA). Adaptar agressivamente à vaga e reframe honesto de autoestudo/projetos/labs
   — **não fabricar vínculo empregatício inexistente**. Ao escrever/revisar qualquer texto de
   candidatura, usar a skill **`escrever-aplicacao`**.
7. **Gate antes de tocar um plugin:** `python scripts/check_contracts.py` precisa passar.

---

## Contrato do plugin (coração do projeto)

Cada plataforma = `app/platforms/<id>/` com:
- **`manifest.py`** — declarativo: `id`, `name`, `channel`, `base_url`/endpoints, captcha
  esperado, `build()` lazy. **Registrar no registry** `platforms/__init__.py` (imports estáticos).
- **`discovery.py`** — `discover(keywords, ctx|session) -> list[JobPosting]` (ausente no canal `email`).
- **`apply.py`** — `apply(job, application, ctx|session, dry_run) -> ApplyResult`.

Schemas normalizados (`JobPosting`, `ApplicationForm`, `FormField`, `ApplyResult`) em
`app/core/schemas.py`. → Detalhe completo do contrato e dos canais: **`SPEC.md` §4** e
**`docs/arquitetura.md`**.

---

## Comandos essenciais

| Comando | Para quê |
|---|---|
| `pip install -r requirements.txt && playwright install chromium` | Setup. |
| `python scripts/login.py <plataforma>` | Login manual → salva sessão (`data/sessions/<id>.json`). |
| `uvicorn app.main:app --reload` | Roda o dashboard (dev). |
| `python scripts/apply_harness.py <id> --keywords "appsec" --dry-run` | Testa 1 plugin isolado (não envia). |
| `python scripts/check_contracts.py` | Gate de contrato dos plugins (sem rede/DB). |

---

## Stack

Python · FastAPI · Jinja2 + HTMX (sem build JS) · SQLModel + SQLite · Playwright (CDP) ·
curl_cffi · WeasyPrint · DeepSeek (SDK `openai`, `base_url=https://api.deepseek.com`;
`deepseek-reasoner` p/ ranking, `deepseek-chat` p/ geração) · 2Captcha.

## Prioridade de plataformas (por taxa de resposta / risco)

Gupy (API) → InHire (API) → Indeed (browser) → Catho (browser) → email direto → **LinkedIn por
último** (anti-bot agressivo). Detalhe e dados em `ideia.md` / `SPEC.md`.

## Adicionar plataforma / mexer no núcleo

- **Plugin novo:** crie `platforms/<id>/` (3 arquivos), registre no registry, valide com
  `check_contracts.py` + `apply_harness.py` em dry-run antes de qualquer envio real.
- **Mudança no `core/`:** afeta todos os plugins — passo pequeno, verifique com o harness.

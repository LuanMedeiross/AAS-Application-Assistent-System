# GUPY — Playbook do plugin (LER ANTES DE MEXER)

> **Fonte de verdade da metodologia da Gupy.** Consulte este arquivo sempre que for alterar
> `discovery.py`, `apply.py` ou `manifest.py`. Descobertas empíricas (2026) — revalide se a Gupy
> mudar. Complementa `docs/plataformas.md` (visão geral multi-plataforma) e `CLAUDE.md` (regras).

Canal: **`api`** para descoberta (HTTP anônimo, sem captcha) + **`browser`** para candidatura
(exige sessão logada do candidato). O plugin **não abre browser sozinho** — recebe `page`/`session`
do harness (`scripts/auto_apply.py` é dono do `BrowserHarness`).

---

## 1. Descoberta de vagas (canal API, anônimo)

**Endpoint:** `GET https://employability-portal.gupy.io/api/v1/jobs`
(é o backend público do `portal.gupy.io`; **não** é `api.gupy.io`, que exige Bearer de empresa.)

**Resposta:** `{ "data": [ {job}, ... ], "pagination": {total, limit, offset} }`

### Parâmetros (estudo empírico)
| Param | Efeito | Observação |
|---|---|---|
| `jobName` | busca textual no título | **é `jobName`, não `name`** (`name` → HTTP 400) |
| `limit` | tamanho da página | **máx. 100** (`>100` → retorna vazio) |
| `offset` | paginação | somar `limit` até esgotar |
| `workplaceType` | `remote` \| `hybrid` \| `on-site` | filtra server-side, **1 valor por request** |
| `isRemoteWork` | `true` | == `workplaceType=remote` |
| `state` | nome COMPLETO ("São Paulo") | "SP" → 0 resultados |
| `city` | nome da cidade | |
| `type` | `vacancy_type_effective` \| `..._internship` \| `..._talent_pool` \| `..._temporary` \| `..._associate` \| `vacancy_legal_entity` | filtra por tipo de vaga |

**NÃO existem** filtros de data/ordenação: `orderBy`, `sort`, `publishedSince` → **HTTP 400**.

### ⚠️ `pagination.total` é FURADO
Reporta só o tamanho da página (capado no `limit`), não o total real. Ex.: "segurança da
informação" com `limit=100` → `total:100`, mas `offset=100` traz +38 (real ≈138).
**Regra: paginar por `offset` até `len(data) < limit`.** (Ver `_fetch_all()`.)

### Campos de cada vaga (→ `JobPosting`)
`id`, `companyId`, `name` (título), `description` (**HTML** — limpar), `careerPageId`,
`careerPageName` (empresa), `careerPageUrl`, `type`, `publishedDate` (ISO), `applicationDeadline`
(data), `isRemoteWork`, `city`, `state`, `country`, `jobUrl` (link direto), `workplaceType`,
`disabilities`, `skills`, `badges` (nem sempre presente).

Mapa: `platform="gupy"`, `external_id=id`, `title=name`, `company=careerPageName`, `url=jobUrl`,
`location=city/state/country` (ou "Remoto"), `description=limpo`, `raw=<objeto cru>`.

**Endpoint de detalhe:** `GET /api/v1/jobs/{id}` — mesmos campos, **sem status** (não serve p/ saber
se está aberta; ver §3).

---

## 2. Metodologia de busca (termos)

- **Multi-termo + dedup por `id`.** Cobertura varia MUITO: "segurança da informação" ≈138,
  "pentest" ≈4, "red team" ≈2, "segurança ofensiva" ≈1. Termos amplos pegam volume; específicos
  pegam precisão. Use vários e deduplique.
- Termos-alvo atuais (segurança ofensiva/AppSec, perfil junior): `pentest`, `appsec`,
  `segurança da informação`, `red team`, `devsecops`, `segurança ofensiva`, `segurança cibernética`,
  `cyber security`.
- Acentos importam no `jobName` (a Gupy casa por texto do título).

---

## 3. Filtros do projeto (recência + aberta) — client-side

A API não filtra data/status; fazemos client-side, na ordem **barato → caro**:

1. **Tipo** (`type ∈ {vacancy_type_effective, vacancy_type_internship}` por padrão — efetiva + estágio).
2. **Modelo** (`workplaceType ∈ {remote, hybrid}` — priorizar remoto; sem presencial puro).
3. **Recência:** descartar `publishedDate` > **28 dias** (há vagas com 1900+ dias listadas!).
4. **Aberta:** ver abaixo. Só roda nos sobreviventes (é o passo caro: 1 GET por vaga).

### ⚠️ Como saber se a vaga está ABERTA
- **`applicationDeadline` é INÚTIL:** fica no futuro mesmo em vaga já encerrada (0/127 no passado
  no estudo). Vaga pode ser fechada antes do prazo ("staff_replacement" etc.).
- **Sinal confiável = status na career page.** A `jobUrl` é **Next.js SSR** e embute:
  ```html
  <script id="__NEXT_DATA__" type="application/json">{ "props":{ "pageProps":{ "job":{
      "id":..., "status":"published" | "closed", ...
  }}}}</script>
  ```
  `status == "published"` → aberta; `"closed"` → encerrada. **Fetch HTTP puro** da `jobUrl` +
  parse do JSON (sem browser). Ver `_is_open()`. Em erro/parse falho → NÃO descarta (evita perder
  vaga por transiente).

Defaults e implementação: `discovery.py` (`DEFAULT_TYPES`, `DEFAULT_WORKPLACES`, `PAGE_LIMIT`,
`_is_recent`, `_is_open`, `_fetch_all`, `discover`).

### Descarte de vagas AFIRMATIVAS exclusivas (fator imutável)
Aplicado pelo orquestrador (`discover_rank.py`), não pela discovery do plugin — é cross-plataforma
(`app/ai/eligibility.py`). Vaga afirmativa EXCLUSIVA (só aceita um grupo: PcD / racial / gênero) é
**descartada** se o candidato não pertence ao grupo (`Profile.demographics()`: pcd/race/gender).
Pré-filtro barato por palavra-chave ("afirmativa", "talentos negros", "[pcd]"…) → só suspeitos vão
para a IA (`deepseek-chat`), que distingue **exclusiva** de "empresa valoriza diversidade/benefício"
(não descarta esses). `cleanup_jobs.py` também remove afirmativas já salvas no banco.

---

## 4. Candidatura (canal browser) — fluxo REAL

**Fixo em toda Gupy; o que muda por empresa são as PERGUNTAS** (respondidas pela IA, ver §5).
Exige sessão logada (`scripts/login.py gupy`). Motor: `run_auto_apply(page, ...)` em `apply.py`,
chamado por `scripts/auto_apply.py`. Detecção de etapa por `_detect_step()`.

### Sequência e seletores
| # | Etapa | Como detectar | Ação / botão |
|---|---|---|---|
| 1 | **Início** (página da vaga) | `a[data-testid="apply-link"]` | clicar "Candidatar-se" |
| 2 | **Revisão de currículo** | etapa "advance" (sem os marcadores abaixo) | botão **"Continuar"** |
| 3 | **Dados adicionais** | `input[name="radioGroupIsIndicatedTitle"]` | radios já vêm "Não" (honesto); fonte opcional em branco; `button[name="saveAndContinueButton"]` **"Salvar e continuar"** |
| 4 | **Landing "Perguntas da empresa"** | `button[aria-label="Responder agora"]` | clicar "Responder agora" |
| 5 | **Perguntas da empresa** | `.curriculum-content` com `textarea/input` | IA responde → preenche → **"Salvar e continuar"** ⚠️ IRREVERSÍVEL |
| 6 | **Modal** | após salvar | **SEMPRE** `button#dialog-save-personalization-step` "Personalizar candidatura" |
| 7 | **"Apresente-se"** | `#personalization-step-text-area` ou `[data-testid="candidate-skill"]` | IA escreve apresentação + escolhe ≤3 skills → **"Finalizar candidatura"** ⚠️ ENVIO |

### Detalhes das perguntas da empresa (etapa 5)
- Só a **PRIMEIRA** `div.curriculum-content` tem as perguntas (extrair com escopo:
  `page.evaluate(EXTRACT_JS, ".curriculum-content")`).
- Cada pergunta = `<h3>N. Enunciado *</h3>` (o `*` = obrigatória) + um campo:
  - **textarea:** `id="input-<enunciado>"`, `name="<enunciado>"`, `maxlength=1000`.
  - **radio (MUI):** `input[name="question-<id>"]` com **`value=""`** (vazio!) — casar pela LABEL
    ("Sim"/"Não"/faixa), não pelo value.
- Aviso "**As respostas não poderão ser editadas depois.**" → por isso o "Salvar e continuar" aqui
  é gated como irreversível.

### Skills (etapa 7)
- Botões `button[data-testid="candidate-skill"]`, cada um com `<div>` = nome da skill.
- Contador "N / 3 habilidades selecionadas" → **máx. 3**. Clicar o botão seleciona.
- Extração: `EXTRACT_JS` devolve `snapshot.skills = {options, max}` → vira `FormQuestion(kind="skills")`.

---

## 5. Como a IA responde (form_agent) — resumo

Filosofia: **responder TODAS as perguntas** (travar em `unknown` inviabiliza automação em massa).
Detalhe completo em `app/ai/form_agent.py`. Regras:
- Dado no PERFIL/EXTRAS → usar direto.
- **Disponibilidade/vontade/logística** (sábados, turnos, viagem, mudança, presencial) → o que a
  empresa quer, quase sempre **"Sim"**.
- **Consentimento/LGPD/autorização** → **sempre "Sim"**.
- **Salário:** pretensão = EXTRAS; **atual/último = pretensão − 8%**; faixa (radio) → a que contém
  o valor.
- **Factual/legal** (já trabalhou aqui? vínculo familiar? PCD?) → **verdade do perfil**. Linha dura:
  **nunca inventar** vínculo/emprego/senioridade/certificação inexistente.
- Texto livre ("apresente-se") → voz humana (HUMANIZE), reaproveitando a carta, idioma da vaga.

EXTRAS vêm de `Profile.to_application_extras()` (pretensão, disponibilidade, PCD, fonte, FAQ livre),
editáveis em `/profile`.

---

## 6. Segurança / gating (NÃO afrouxar)

- **Envio real** só com `ALLOW_REAL_SUBMIT=true` **ou** flag `--real` no `auto_apply.py`.
- `--real` envia **direto** (sem perguntar); `--real --confirm` pausa em cada passo irreversível.
- **Pontos irreversíveis:** "Salvar e continuar" das perguntas da empresa (trava respostas) e
  "Finalizar candidatura" (envio). Sem `allow_real` → DRY-RUN: preenche tudo e **para** antes.
- Cada campo preenchido e o resultado vão para `AuditLog` (`action="auto_apply"`).

---

## 7. Gotchas (armadilhas já resolvidas — não regredir)

- **SPA de URL única:** as etapas trocam sem mudar a URL (`.../steps/.../curriculum`). Não confie
  na URL para saber a etapa; detecte por seletores (`_detect_step`) e, ao avançar, **espere a
  ASSINATURA da etapa mudar** (`_advance` compara `_sig` antes/depois) — a Gupy salva async e o
  botão fica **desabilitado** enquanto salva (reclicar dá timeout).
- **Enunciado da pergunta** está no `<h3>`/`<legend>`, não no campo. O extrator prioriza
  heading/legend do container mais próximo (senão pegava "Máx. 1000 caracteres" ou a 1ª opção).
- **Radios MUI** têm `value=""` → casar pela label visível, clicando o `<label>` (input é oculto).
- **Botão "Salvar e continuar"** só habilita quando todos os obrigatórios estão preenchidos no
  estado do React — `.fill()` (textarea) e clique no `<label>` (radio) disparam os eventos certos.

---

## 8. Lacunas conhecidas (TODO)

- **Upload do CV sob medida NÃO está plugado:** a candidatura usa o **CV do perfil Gupy**, não o
  `cv_job_N.pdf` adaptado. Falta subir no dropzone da etapa de revisão de currículo (etapa 2) antes
  do "Continuar". As respostas/apresentação/skills JÁ vão sob medida.
- **Captcha** ainda não acionado no loop (usar `core/captcha.py` se a Gupy bloquear).

---

## 9. Arquivos

- `discovery.py` — busca + filtros (recência/aberta/tipo/modelo).
- `apply.py` — `run_auto_apply()` (fluxo browser) + `prepare()/submit()` (fluxo fila antigo).
- `manifest.py` — declarativo (id/name/channel/endpoints/build).
- Núcleo compartilhado: `core/form_extract.py` (DOM→perguntas), `core/form_fill.py` (preencher),
  `ai/form_agent.py` (responder), `core/browser.py` (Chromium CDP), `core/session.py` (sessão).
- Scripts: `scripts/login.py gupy`, `scripts/discover_rank.py gupy`, `scripts/tailor_job.py`,
  `scripts/auto_apply.py <id> [--real] [--confirm]`, `scripts/snapshot_form.py` (dev: dump do DOM).

# Application Assistant

App local que automatiza candidatura a vagas com IA (DeepSeek) + automação de navegador/API.
Ciclo: **descobrir → ranquear → adaptar CV/carta → preencher → enviar**, com revisão humana.

> Documentação: `ideia.md` (visão) · `SPEC.md` (o quê) · `docs/arquitetura.md` (como) ·
> `docs/design.md` (UI) · `ATS.md` (regras de currículo) · `CLAUDE.md` (guia + Sistema Karpathy).

## Licença

[Apache-2.0](LICENSE). Fornecido **"COMO ESTÁ", sem garantia** (ver seções 7–8 da licença).

## ⚠️ Uso responsável (leia antes de usar)

Esta é uma ferramenta **local, single-user**, para **uso pessoal**. Ao usá-la, **você** é o único
responsável por como a opera:

- **Respeite os Termos de Serviço** de cada plataforma (Gupy, InHire, Indeed, LinkedIn etc.).
  Automação pode violar o ToS e resultar em **bloqueio da sua conta** — o risco é seu.
- **Não fabrique informação.** O projeto foi desenhado para adaptar honestamente experiências e
  projetos reais, **nunca** inventar vínculo, cargo, senioridade ou certificação (ver `ATS.md`).
- **Seus dados são seus.** CV, credenciais e cookies de sessão ficam **só na sua máquina**
  (`.env`, `data/`, `curriculum/` são gitignorados). Não commite dados pessoais.
- **Revisão humana por padrão.** O envio real exige aprovação explícita; mantenha assim até
  confiar plenamente no comportamento.

Os mantenedores não se responsabilizam por bloqueios de conta, uso indevido ou qualquer dano
decorrente do uso desta ferramenta.

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# (Fase 2+) playwright install chromium
copy .env.example .env   # preencha DEEPSEEK_API_KEY, CAPTCHA_API_KEY, SMTP
```

> Nota: a Fase 1 usa só o subconjunto leve (fastapi/uvicorn/sqlmodel/jinja2/openai). As demais
> deps (playwright, curl_cffi, 2captcha) entram nas fases seguintes. PDF é via Chromium.

## Popular o Profile

```powershell
# Opção A — seed a partir do CV já estruturado:
.\.venv\Scripts\python.exe scripts\seed_profile.py

# Opção B — importar do export oficial do LinkedIn (ZIP ou diretório de CSVs):
.\.venv\Scripts\python.exe scripts\import_linkedin.py "C:\caminho\Basic_LinkedInDataExport.zip"
```

## Rodar o dashboard

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
# abrir http://127.0.0.1:8000/profile
```

## Estado

**Fase 1 concluída** — Esqueleto FastAPI + HTMX, SQLite, modelos, seed do CV-mestre
(`curriculum/`), parser do export do LinkedIn, cliente DeepSeek + sugestão de senioridade,
dashboard de Profile.

**Fase 2 concluída** — Núcleo do harness (`app/core/`): Chromium único via CDP + stealth
(`browser.py`/`stealth.py`), sessão manual reutilizável (`session.py`), HTTP com TLS
impersonation (`http_client.py`), pipeline 2Captcha (`captcha.py`), runner base com circuit
breaker (`runner.py`). Scripts: `login.py` (login manual → sessão), `apply_harness.py`
(smoke/dry-run isolado), `check_contracts.py` (gate de plugins).

```powershell
# testar o harness de navegador:
.\.venv\Scripts\python.exe scripts\apply_harness.py gupy
# salvar sessão de uma plataforma (login manual):
.\.venv\Scripts\python.exe scripts\login.py gupy
```

**Fase 3 em andamento** — Plugin Gupy (canal `api`). **Discovery concluído e verificado** com
dados reais: `app/platforms/gupy/` (manifest + discovery) usa o endpoint público
`employability-portal.gupy.io/api/v1/jobs?jobName=`. Testar:
```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe scripts\apply_harness.py gupy --keywords "appsec,pentest,red team"
```
Falta o **apply** da Gupy (exige a sessão logada do candidato — rodar `scripts/login.py gupy`).

**Fase 4 (ranking) concluída** — `ai/ranker.py` (DeepSeek `reasoner`, o modelo mais forte)
pontua cada vaga 0–100 vs. perfil, penalizando descompasso de senioridade. Fluxo completo em
`scripts/discover_rank.py` (discover → salva no DB → ranqueia) e página `/jobs` no dashboard
ordenada por score.
```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe scripts\discover_rank.py gupy --keywords "appsec,pentest,red team"
# depois abra http://127.0.0.1:8000/jobs
```

**Fase 5 (geração + PDF) concluída** — `ai/tailor.py` gera CV + carta sob medida no idioma da
vaga (ATS + HUMANIZE + anti-fabricação, DeepSeek `reasoner`); `pdf/render.py` renderiza o CV em
PDF via Chromium. `scripts/tailor_job.py [job_id]` gera tudo e registra a `Application`; a página
`/jobs` mostra o CV/carta e serve o PDF.
```powershell
.\.venv\Scripts\python.exe scripts\tailor_job.py        # usa a vaga de maior score
```

**Fase 6 (fila de aprovação + apply) concluída** — `/queue` no dashboard com Preparar/Aprovar/
Rejeitar; `platforms/gupy/apply.py` com trava dupla (aprovação humana + flag `ALLOW_REAL_SUBMIT`,
padrão `false` → dry-run); `core/audit.py` registra tudo. Envio real é **assistido/supervisionado**
via `scripts/apply_job.py <job_id>` (abre a página logada para você concluir). **Fatia vertical
completa:** descobrir → ranquear → gerar CV/carta → revisar → aprovar.

```powershell
.\.venv\Scripts\python.exe scripts\login.py gupy      # 1x: salva a sessão
# no .env: ALLOW_REAL_SUBMIT=true  (só quando for enviar de verdade, supervisionando)
.\.venv\Scripts\python.exe scripts\apply_job.py 2     # envio assistido
```

**Fase 7 em andamento** — Plugin **InHire** (canal `api`, por empresa/tenant) construído e
verificado: `app/platforms/inhire/` usa `api.inhire.app/job-posts/public/pages/lean` com header
`X-Tenant`. Configure as empresas-alvo em `INHIRE_TENANTS` no `.env`. Registrado no registry
(agora: gupy, inhire).

Restante da Fase 7 (melhor construído durante o uso real, "aplicar e consertar"): plugins de
canal `browser` (Indeed/Catho/LinkedIn — anti-bot, exigem login), canal `email` (SMTP) e o modo
automático opcional com filtros.

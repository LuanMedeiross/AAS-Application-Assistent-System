# Application Assistant

App local que automatiza candidatura a vagas com IA (DeepSeek) + automação de navegador/API.
Ciclo: **descobrir → ranquear → adaptar CV/carta → preencher → enviar**, com revisão humana.

> Documentação: `ideia.md` (visão) · `SPEC.md` (o quê) · `docs/arquitetura.md` (como) ·
> `docs/design.md` (UI) · `ATS.md` (regras de currículo) · `CLAUDE.md` (guia + Sistema Karpathy).

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# (Fase 2+) playwright install chromium
copy .env.example .env   # preencha DEEPSEEK_API_KEY, CAPTCHA_API_KEY, SMTP
```

> Nota: a Fase 1 usa só o subconjunto leve (fastapi/uvicorn/sqlmodel/jinja2/openai). As demais
> deps (playwright, curl_cffi, weasyprint, 2captcha) entram nas fases seguintes.

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

## Estado (Fase 1 concluída)

- Esqueleto FastAPI + HTMX, SQLite, modelos (Profile/Job/Application/PlatformSession/AuditLog).
- Seed do CV-mestre (`curriculum/`), parser do export do LinkedIn, cliente DeepSeek + sugestão
  de senioridade.
- Dashboard de Profile (ver/editar/salvar).

Próximo: **Fase 2** — núcleo do harness (browser stealth via CDP, sessão, captcha, runner).

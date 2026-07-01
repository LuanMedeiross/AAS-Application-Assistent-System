# Plataformas — notas técnicas de discovery/apply

> Mecânica confirmada por plataforma (endpoints, params, quirks). Fonte de verdade para os
> plugins em `app/platforms/<id>/`. Descobertas empíricas — revalidar se a plataforma mudar.

## Gupy — canal `api` (discovery confirmado)

**Descoberta de vagas (público, sem auth, sem captcha):**
```
GET https://employability-portal.gupy.io/api/v1/jobs?jobName=<keyword>&offset=0&limit=10
```
- Param de busca é **`jobName`** (usar `name` retorna 400). `offset`/`limit` paginam.
- Sem parâmetros retorna todas as vagas (200). Resposta: `{"data": [ {job}, ... ]}`.
- Host: `employability-portal.gupy.io` (é o backend público do `portal.gupy.io`; NÃO é o
  `api.gupy.io`, que exige Bearer token de empresa/Enterprise).

**Campos por vaga (relevantes):**
`id`, `companyId`, `name` (título), `description` (HTML), `careerPageId`, `careerPageName`
(empresa), `careerPageUrl`, `jobUrl` (link direto da vaga), `type`, `publishedDate`,
`applicationDeadline`, `isRemoteWork`, `workplaceType`, `city`, `state`, `country`, `skills`,
`badges`.

**Mapa → `JobPosting`:** `platform="gupy"`, `external_id=id`, `title=name`, `company=careerPageName`,
`url=jobUrl`, `location=city/state/country`, `description=description` (limpar HTML), `raw=<objeto>`.

**Discovery por cargos-alvo:** uma chamada por keyword do Profile (`appsec`, `pentest`,
`segurança`, `red team`…), paginando via `offset`; deduplica por `id`.

**Apply (a confirmar na implementação):** a candidatura provavelmente exige a **sessão logada do
candidato** (cookies) — Candidatura Rápida via `api.gupy.io/api/v2/applications/.../quick-apply`
autenticada pela sessão, ou via a career page (`jobUrl`) com a sessão salva. Definir no passo de
apply da Fase 3/6.

> Nota de encoding: a resposta é UTF-8; ao imprimir no console do Windows pode aparecer mojibake,
> mas `response.json()` no código entrega unicode correto. Descrições vêm em HTML — limpar tags.

## InHire — canal `api` (a pesquisar)
API pública documentada em `docs.inhire.com.br` (inscrição em vaga). Detalhar na expansão (Fase 7).

## Indeed / Catho / LinkedIn — canal `browser`
Sem API pública aberta de candidato. Discovery/apply via navegador stealth + sessão manual;
captcha via `core/captcha.py` sob bloqueio. LinkedIn por último (anti-bot agressivo).

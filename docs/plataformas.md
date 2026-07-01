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

**Parâmetros da busca (estudo empírico):**
- `jobName` (texto, obrigatório p/ filtrar), `limit` (**máx. 100**; >100 → vazio), `offset` (pagina).
- `pagination.total` é **furado** (reporta só o tamanho da página) — paginar por `offset` até vir
  menos que `limit`.
- Filtros server-side que funcionam (1 valor cada): `workplaceType` (`remote`|`hybrid`|`on-site`),
  `isRemoteWork=true`, `state` (nome completo, ex. "São Paulo"; "SP"→0), `city`, `type`
  (`vacancy_type_effective`|`vacancy_type_internship`|`vacancy_type_talent_pool`|…).
- **Não** há filtro server-side de data/status: `orderBy`/`sort`/`publishedSince` → HTTP 400.

**Regra do projeto (recência + aberta), aplicada client-side no discovery:**
- Tipo/modelo: como a API só aceita 1 valor, filtramos client-side. Padrão: `type ∈ {effective,
  internship}` e `workplaceType ∈ {remote, hybrid}` (priorizar remoto).
- Recência: descartar `publishedDate` > 28 dias (há vagas com 1900+ dias listadas).
- **Aberta:** `applicationDeadline` é INÚTIL (fica no futuro mesmo em vaga encerrada). O sinal
  confiável é o **status na career page**: ela é Next.js SSR e embute em
  `<script id="__NEXT_DATA__">` o `props.pageProps.job.status` = `published` (aberta) | `closed`
  (encerrada). Fetch HTTP puro da `jobUrl` + parse do JSON. Ver `_is_open()` no discovery.

## InHire — canal `api` (discovery confirmado, POR EMPRESA)

InHire é **multi-tenant**: não há busca global pública; cada empresa é um `tenant`. O endpoint
público exige o header **`X-Tenant: <empresa>`** e devolve **todas** as vagas daquela empresa
(a busca por texto é client-side). Descobrimos por uma **lista de empresas-alvo**.

```
GET https://api.inhire.app/job-posts/public/pages/lean        (X-Tenant: <empresa>)  -> lista enxuta
GET https://api.inhire.app/job-posts/public/pages/{jobId}     (X-Tenant: <empresa>)  -> detalhe
```
- **lean** (por vaga): `displayName` (título), `jobId`, `link` (url), `careerPage.name` (empresa).
- **detalhe**: `description` (HTML), `location`, `workplaceType`, `contractType`.
- **Filtro** por keyword é feito no título (`displayName`) no nosso código.
- **Empresas-alvo**: configuráveis via `INHIRE_TENANTS` no `.env` (slugs, ex.: `empresa` de
  `empresa.inhire.app`). Sem tenants configurados, o discovery do InHire retorna vazio.

**Mapa → `JobPosting`:** `platform="inhire"`, `external_id=jobId`, `title=displayName`,
`company=careerPage.name`, `url=link`, `location`/`description` do detalhe.

## Indeed / Catho / LinkedIn — canal `browser`
Sem API pública aberta de candidato. Discovery/apply via navegador stealth + sessão manual;
captcha via `core/captcha.py` sob bloqueio. LinkedIn por último (anti-bot agressivo).

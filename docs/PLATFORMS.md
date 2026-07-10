# Platforms — technical notes on discovery/apply

> Confirmed mechanics per platform (endpoints, params, quirks). Source of truth for the
> plugins in `app/platforms/<id>/`. Empirical findings — revalidate if the platform changes.

## Gupy — channel `api` (discovery confirmed)

**Job discovery (public, no auth, no captcha):**
```
GET https://employability-portal.gupy.io/api/v1/jobs?jobName=<keyword>&offset=0&limit=10
```
- The search param is **`jobName`** (using `name` returns 400). `offset`/`limit` paginate.
- With no parameters it returns all jobs (200). Response: `{"data": [ {job}, ... ]}`.
- Host: `employability-portal.gupy.io` (this is the public backend of `portal.gupy.io`; it is NOT
  `api.gupy.io`, which requires a company/Enterprise Bearer token).

**Fields per job (relevant ones):**
`id`, `companyId`, `name` (title), `description` (HTML), `careerPageId`, `careerPageName`
(company), `careerPageUrl`, `jobUrl` (direct job link), `type`, `publishedDate`,
`applicationDeadline`, `isRemoteWork`, `workplaceType`, `city`, `state`, `country`, `skills`,
`badges`.

**Map → `JobPosting`:** `platform="gupy"`, `external_id=id`, `title=name`, `company=careerPageName`,
`url=jobUrl`, `location=city/state/country`, `description=description` (clean the HTML), `raw=<object>`.

**Discovery by target roles:** one call per Profile keyword (`appsec`, `pentest`,
`segurança`, `red team`…), paginating via `offset`; deduplicate by `id`.

**Apply (to be confirmed in the implementation):** the application likely requires the candidate's
**logged-in session** (cookies) — Quick Apply via `api.gupy.io/api/v2/applications/.../quick-apply`
authenticated by the session, or via the career page (`jobUrl`) with the saved session. To be decided in the
apply step of Phase 3/6.

> Encoding note: the response is UTF-8; when printing to the Windows console it may show up as mojibake,
> but `response.json()` in the code delivers correct unicode. Descriptions come as HTML — strip the tags.

**Search parameters (empirical study):**
- `jobName` (text, required to filter), `limit` (**max. 100**; >100 → empty), `offset` (paginates).
- `pagination.total` is **broken** (it only reports the page size) — paginate by `offset` until
  fewer than `limit` come back.
- Server-side filters (**multi-value by comma** = OR; distinct params = AND): `workplaceType`
  (`remote`|`hybrid`|`on-site`), `isRemoteWork=true`, `state` (full name, e.g. "São Paulo"; "SP"→0),
  `city`, `type` (`vacancy_type_effective`|`vacancy_type_internship`|`vacancy_type_talent_pool`|…),
  `companyId` (enumerates a whole company). Any unknown param → HTTP 400 (strict allowlist).
- There is **no** server-side date/status/ordering filter: `orderBy`/`sort`/`publishedSince`/`status`
  → HTTP 400. Full detail + endpoints in `app/platforms/gupy/GUPY.md`.

**Project rule (recency + open):**
- Type/model: pushed **server-side** via comma multi-value (`type=eff,int` + `workplaceType=remote,hybrid`),
  so pagination isn't wasted on discarded jobs. Default: `type ∈ {effective, internship}` and
  `workplaceType ∈ {remote, hybrid}` (prioritize remote). A client-side re-check stays as a safety net.
- Recency: discard `publishedDate` > 28 days (there are jobs listed with 1900+ days).
- **Open:** `applicationDeadline` is USELESS (it stays in the future even on a closed job). The
  reliable signal is the **status on the career page**: it is Next.js SSR and embeds in
  `<script id="__NEXT_DATA__">` the `props.pageProps.job.status` = `published` (open) | `closed`
  (closed). Plain HTTP fetch of the `jobUrl` + parse the JSON. See `_is_open()` in discovery.

## InHire — channel `api` (discovery confirmed, PER COMPANY)

InHire is **multi-tenant**: there is no public global search; each company is a `tenant`. The public
endpoint requires the header **`X-Tenant: <empresa>`** and returns **all** the jobs for that company
(the text search is client-side). We discover through a **list of target companies**.

```
GET https://api.inhire.app/job-posts/public/pages/lean        (X-Tenant: <empresa>)  -> lean list
GET https://api.inhire.app/job-posts/public/pages/{jobId}     (X-Tenant: <empresa>)  -> detail
```
- **lean** (per job): `displayName` (title), `jobId`, `link` (url), `careerPage.name` (company).
- **detail**: `description` (HTML), `location`, `workplaceType`, `contractType`.
- **Filtering** by keyword is done on the title (`displayName`) in our code.
- **Target companies**: a curated, live-validated list in `app/platforms/inhire/tenants.py`
  (`TENANTS`, ~96 companies, cyber-security first). `INHIRE_TENANTS` in `.env` **extends** it.
  No global search exists, so coverage == the tenant list. Detail in `app/platforms/inhire/INHIRE.md`.

**Map → `JobPosting`:** `platform="inhire"`, `external_id=jobId`, `title=displayName`,
`company=careerPage.name`, `url=link`, `location`/`description` from the detail.

## Indeed / Catho / LinkedIn — channel `browser`
No open public candidate API. Discovery/apply via stealth browser + manual session;
captcha via `core/captcha.py` under a lock. LinkedIn last (aggressive anti-bot).

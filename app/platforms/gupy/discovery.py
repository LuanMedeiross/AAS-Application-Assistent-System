"""Descoberta de vagas na Gupy (canal api).

→ METODOLOGIA COMPLETA (API, params, termos, filtros, fluxo): ver `app/platforms/gupy/GUPY.md`.
  LEIA antes de alterar qualquer coisa da Gupy.

Endpoint público confirmado (sem auth, sem captcha):
    GET https://employability-portal.gupy.io/api/v1/jobs?jobName=<kw>&offset=&limit=

Uma chamada por keyword dos cargos-alvo, paginando por offset; deduplica por id.
Não abre navegador (contrato do plugin). `session` é injetada pelo harness; se ausente,
cria uma sessão HTTP (curl_cffi) — discovery da Gupy é anônimo.
"""
from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from ...core.http_client import HTTP_ERRORS, new_session
from ...core.schemas import JobPosting

log = logging.getLogger(__name__)

JOBS_URL = "https://employability-portal.gupy.io/api/v1/jobs"

# Filtros padrão (decisão do usuário). `type` e `workplaceType` são filtrados client-side porque
# a API só aceita 1 valor por request. Ver docs/PLATFORMS.md (estudo da API).
DEFAULT_TYPES = frozenset({"vacancy_type_effective", "vacancy_type_internship"})  # efetiva + estágio
DEFAULT_WORKPLACES = frozenset({"remote", "hybrid"})  # priorizar remoto (+ híbrido; sem presencial puro)
PAGE_LIMIT = 100  # máximo aceito pela API (limit>100 retorna vazio)

# A career page da Gupy é server-rendered (Next.js) e embute o status real da vaga em
# __NEXT_DATA__: props.pageProps.job.status == "published" (aberta) | "closed" (encerrada).
# É o único sinal confiável de "ainda aberta" (a API pública de busca lista vagas encerradas,
# e applicationDeadline pode estar no futuro mesmo com a vaga fechada antes do prazo).
_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)


def _clean_html(text: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _is_recent(job: dict, max_age_days: int) -> bool:
    """True se a vaga foi publicada nos últimos `max_age_days` dias (sem data → mantém)."""
    pd = job.get("publishedDate")
    if not pd:
        return True
    try:
        dt = datetime.fromisoformat(pd.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return True
    if dt.tzinfo is None:  # publishedDate sem fuso (ex.: data pura) → assume UTC p/ poder comparar
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= datetime.now(timezone.utc) - timedelta(days=max_age_days)


def _is_open(session, job_url: str) -> bool:
    """True se a vaga ainda aceita candidaturas (status "published" no __NEXT_DATA__).
    Em erro/parse falho, NÃO descarta (retorna True) para não perder vaga por transiente."""
    if not job_url:
        return True
    try:
        r = session.get(job_url, timeout=25)
        if r.status_code != 200:
            return True
        m = _NEXT_DATA.search(r.text)
        if not m:
            return True
        job = (((json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}).get("job") or {})
        status = job.get("status")
        return status is None or status == "published"
    except HTTP_ERRORS as e:  # noqa: PERF203
        log.debug("open-check falhou (%s): %s", job_url, e)
        return True


def _location(job: dict) -> str:
    if job.get("isRemoteWork"):
        return "Remoto"
    parts = [job.get("city"), job.get("state"), job.get("country")]
    return ", ".join(p for p in parts if p)


def _to_posting(job: dict) -> JobPosting:
    return JobPosting(
        platform="gupy",
        external_id=str(job.get("id", "")),
        url=job.get("jobUrl") or job.get("careerPageUrl") or "",
        title=job.get("name", ""),
        company=job.get("careerPageName", ""),
        location=_location(job),
        description=_clean_html(job.get("description")),
        raw=job,
    )


def _fetch_all(session, kw: str, max_pages: int) -> list[dict]:
    """Pagina uma keyword por offset até esgotar (pagination.total é furado — não confiar nele)."""
    jobs: list[dict] = []
    offset = 0
    for _ in range(max_pages):
        try:
            r = session.get(
                JOBS_URL, params={"jobName": kw, "offset": offset, "limit": PAGE_LIMIT}, timeout=25
            )
        except HTTP_ERRORS as e:  # noqa: PERF203
            log.warning("Gupy discovery falhou (kw=%s): %s", kw, e)
            break
        if r.status_code != 200:
            log.info("Gupy discovery kw=%s offset=%s -> HTTP %s", kw, offset, r.status_code)
            break
        data = (r.json() or {}).get("data") or []
        jobs.extend(data)
        if len(data) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
    return jobs


def discover(
    keywords: list[str],
    session=None,
    *,
    types: frozenset = DEFAULT_TYPES,
    workplaces: frozenset = DEFAULT_WORKPLACES,
    max_age_days: int = 28,
    check_open: bool = True,
    max_pages: int = 10,
) -> list[JobPosting]:
    """Busca vagas por keyword e devolve JobPosting[] deduplicado por id.

    Pipeline (barato → caro): pagina tudo (limit=100 + offset) → filtra por TIPO (efetiva/estágio)
    e MODELO (remoto/híbrido) client-side → filtra RECÊNCIA (≤max_age_days) → verifica se ainda
    está ABERTA (status "published" no __NEXT_DATA__). Regra do projeto: recência + aberta.
    `types`/`workplaces` vazios = sem esse filtro. Ver docs/PLATFORMS.md.
    """
    session = session or new_session()
    seen_raw: dict[str, dict] = {}
    for kw in keywords:
        for job in _fetch_all(session, kw, max_pages):
            jid = str(job.get("id", ""))
            if jid and jid not in seen_raw:
                seen_raw[jid] = job

    total = len(seen_raw)
    kept, dropped_type, dropped_old, closed = [], 0, 0, 0
    for job in seen_raw.values():
        if types and job.get("type") not in types:
            dropped_type += 1
            continue
        if workplaces and job.get("workplaceType") not in workplaces:
            dropped_type += 1
            continue
        if not _is_recent(job, max_age_days):
            dropped_old += 1
            continue
        posting = _to_posting(job)
        if check_open and not _is_open(session, posting.url):
            closed += 1
            continue
        kept.append(posting)

    log.info(
        "Gupy discovery: %d encontradas → -%d tipo/modelo → -%d antigas(>%dd) → -%d encerradas "
        "→ %d finais",
        total, dropped_type, dropped_old, max_age_days, closed, len(kept),
    )
    return kept

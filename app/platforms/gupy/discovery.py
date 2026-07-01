"""Descoberta de vagas na Gupy (canal api).

Endpoint público confirmado (sem auth, sem captcha):
    GET https://employability-portal.gupy.io/api/v1/jobs?jobName=<kw>&offset=&limit=

Uma chamada por keyword dos cargos-alvo, paginando por offset; deduplica por id.
Não abre navegador (contrato do plugin). `session` é injetada pelo harness; se ausente,
cria uma sessão HTTP (curl_cffi) — discovery da Gupy é anônimo.
"""
from __future__ import annotations

import html
import logging
import re

from ...core.http_client import HTTP_ERRORS, new_session
from ...core.schemas import JobPosting

log = logging.getLogger(__name__)

JOBS_URL = "https://employability-portal.gupy.io/api/v1/jobs"


def _clean_html(text: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


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


def discover(
    keywords: list[str],
    session=None,
    *,
    limit: int = 10,
    max_pages: int = 3,
) -> list[JobPosting]:
    """Busca vagas para cada keyword e devolve JobPosting[] deduplicado por id."""
    session = session or new_session()
    seen: dict[str, JobPosting] = {}
    for kw in keywords:
        offset = 0
        for _ in range(max_pages):
            try:
                r = session.get(
                    JOBS_URL,
                    params={"jobName": kw, "offset": offset, "limit": limit},
                    timeout=25,
                )
            except HTTP_ERRORS as e:  # noqa: PERF203
                log.warning("Gupy discovery falhou (kw=%s): %s", kw, e)
                break
            if r.status_code != 200:
                log.info("Gupy discovery kw=%s offset=%s -> HTTP %s", kw, offset, r.status_code)
                break
            data = (r.json() or {}).get("data") or []
            if not data:
                break
            for job in data:
                jid = str(job.get("id", ""))
                if jid and jid not in seen:
                    seen[jid] = _to_posting(job)
            if len(data) < limit:
                break
            offset += limit
    log.info("Gupy discovery: %d vaga(s) para %d keyword(s)", len(seen), len(keywords))
    return list(seen.values())

"""Descoberta de vagas no InHire (canal api). Ver docs/PLATFORMS.md.

InHire é POR EMPRESA (tenant): o endpoint público exige header X-Tenant=<empresa> e devolve
todas as vagas daquela empresa (a busca é client-side). Então descobrimos por uma lista curada de
empresas-alvo (`tenants.py`, validada ao vivo) e filtramos por keyword no título. `INHIRE_TENANTS`
no `.env` estende essa lista.

  GET https://api.inhire.app/job-posts/public/pages/lean   (X-Tenant: <empresa>)  -> lista enxuta
  GET https://api.inhire.app/job-posts/public/pages/{jobId} (X-Tenant: <empresa>) -> detalhe (descrição)
"""
from __future__ import annotations

import html
import logging
import re

from ...config import settings
from ...core.http_client import HTTP_ERRORS, new_session
from ...core.schemas import JobPosting
from .tenants import TENANTS

log = logging.getLogger(__name__)

API = "https://api.inhire.app"


def _clean_html(text: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def discover(
    keywords: list[str],
    session=None,
    *,
    tenants: list[str] | None = None,
    max_detail: int = 40,
) -> list[JobPosting]:
    session = session or new_session()
    if tenants is None:
        # Curated plugin list is the source of truth; INHIRE_TENANTS (.env) EXTENDS it (dedup,
        # order preserved) so a private/extra tenant can be added without editing code. See tenants.py.
        tenants = list(dict.fromkeys([*TENANTS, *settings.inhire_tenants]))
    kws = [k.lower() for k in keywords]
    seen: dict[str, JobPosting] = {}
    for tenant in tenants:
        hdr = {"X-Tenant": tenant}
        try:
            r = session.get(f"{API}/job-posts/public/pages/lean", headers=hdr, timeout=25)
        except HTTP_ERRORS as e:
            log.warning("InHire lean falhou (tenant=%s): %s", tenant, e)
            continue
        if r.status_code != 200:
            log.warning("InHire lean tenant=%s -> HTTP %s (%s)", tenant, r.status_code, r.text[:80])
            continue
        items = r.json() or []
        matches = [it for it in items if any(k in (it.get("displayName", "").lower()) for k in kws)]
        for it in matches[:max_detail]:
            jid = it.get("jobId")
            if not jid or jid in seen:
                continue
            detail = {}
            try:
                dr = session.get(f"{API}/job-posts/public/pages/{jid}", headers=hdr, timeout=25)
                if dr.status_code == 200:
                    detail = dr.json() or {}
            except HTTP_ERRORS:
                pass
            company = (it.get("careerPage") or {}).get("name") or tenant
            seen[jid] = JobPosting(
                platform="inhire", external_id=jid,
                url=it.get("link", ""),
                title=it.get("displayName", ""),
                company=company,
                location=detail.get("location", ""),
                description=_clean_html(detail.get("description")),
                raw={"tenant": tenant, "lean": it},
            )
    log.info("InHire discovery: %d vaga(s) em %d empresa(s)", len(seen), len(tenants))
    return list(seen.values())

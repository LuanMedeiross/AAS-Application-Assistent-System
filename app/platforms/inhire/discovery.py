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
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from ...config import settings
from ...core.http_client import HTTP_ERRORS, new_session
from ...core.schemas import JobPosting
from .tenants import TENANTS

log = logging.getLogger(__name__)

API = "https://api.inhire.app"

# Varremos ~96 tenants por busca (a InHire não tem busca global). Paralelizamos com um teto de
# conexões concorrentes à API. Cada worker usa uma sessão HTTP própria da sua thread.
_MAX_WORKERS = 10
_tls = threading.local()


def _tls_session():
    s = getattr(_tls, "session", None)
    if s is None:
        s = _tls.session = new_session()
    return s

# Filtros do projeto (espelham a Gupy). Ao contrário da Gupy, aqui TUDO sai do `detail` que já
# baixamos por vaga — inclusive `status` (aberta/fechada), que na Gupy custa 1 GET no HTML. Grátis.
DEFAULT_WORKPLACES = frozenset({"remote", "hybrid"})  # priorizar remoto (+ híbrido; sem presencial)


def _norm_workplace(wt: str | None) -> str:
    """Normaliza o workplaceType da InHire ("Remote"/"Hybrid"/"On-site") para o padrão minúsculo."""
    return (wt or "").strip().lower().replace(" ", "-")


def _is_recent(detail: dict, max_age_days: int) -> bool:
    """True se publicada nos últimos `max_age_days` dias (sem data/parse falho → mantém)."""
    pd = detail.get("lastPublishedAt") or detail.get("publishedAt")  # mais recente (republicação conta)
    if not pd:
        return True
    try:
        dt = datetime.fromisoformat(str(pd).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= datetime.now(timezone.utc) - timedelta(days=max_age_days)


def _clean_html(text: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _scan_tenant(tenant, kws, workplaces, max_age_days, check_open, max_detail, session=None):
    """Varre 1 tenant: lean → filtra por keyword → detail → filtros modelo/recência/aberta.
    Retorna (postings, dropped_model, dropped_old, closed). Sem `session`, usa a sessão da thread
    (caminho paralelo); com `session`, reutiliza a injetada (caminho sequencial do harness)."""
    session = session or _tls_session()
    out: list[JobPosting] = []
    dropped_model = dropped_old = closed = 0
    hdr = {"X-Tenant": tenant}
    try:
        r = session.get(f"{API}/job-posts/public/pages/lean", headers=hdr, timeout=25)
    except HTTP_ERRORS as e:
        log.warning("InHire lean falhou (tenant=%s): %s", tenant, e)
        return out, dropped_model, dropped_old, closed
    if r.status_code != 200:
        log.warning("InHire lean tenant=%s -> HTTP %s (%s)", tenant, r.status_code, r.text[:80])
        return out, dropped_model, dropped_old, closed
    items = r.json() or []
    matches = [it for it in items if any(k in (it.get("displayName", "").lower()) for k in kws)]
    for it in matches[:max_detail]:
        jid = it.get("jobId")
        if not jid:
            continue
        detail = {}
        try:
            dr = session.get(f"{API}/job-posts/public/pages/{jid}", headers=hdr, timeout=25)
            if dr.status_code == 200:
                detail = dr.json() or {}
        except HTTP_ERRORS:
            pass

        # Filtros sobre o detail (desconhecido → mantém, p/ não perder vaga por transiente):
        status = detail.get("status")
        if check_open and status is not None and status != "published":
            closed += 1
            continue
        wt = _norm_workplace(detail.get("workplaceType"))
        if workplaces and wt and wt not in workplaces:
            dropped_model += 1
            continue
        if not _is_recent(detail, max_age_days):
            dropped_old += 1
            continue

        company = (it.get("careerPage") or {}).get("name") or tenant
        # Guarda no raw só o subconjunto útil do detail (o apply futuro usa `settings.fields`/
        # `requiredFields`; ver INHIRE.md §2). Enxuga o `settings.email` (template HTML enorme).
        _settings = detail.get("settings") or {}
        raw_detail = {
            "status": detail.get("status"),
            "workplaceType": detail.get("workplaceType"),
            "contractType": detail.get("contractType"),
            "publishedAt": detail.get("publishedAt"),
            "lastPublishedAt": detail.get("lastPublishedAt"),
            "settings": {k: v for k, v in _settings.items() if k != "email"},
        }
        out.append(JobPosting(
            platform="inhire", external_id=jid,
            url=it.get("link", ""),
            title=it.get("displayName", ""),
            company=company,
            location=detail.get("location", ""),
            description=_clean_html(detail.get("description")),
            raw={"tenant": tenant, "lean": it, "detail": raw_detail},
        ))
    return out, dropped_model, dropped_old, closed


def discover(
    keywords: list[str],
    session=None,  # aceito pelo contrato do plugin; a varredura usa sessão por thread (discovery anônima)
    *,
    tenants: list[str] | None = None,
    workplaces: frozenset = DEFAULT_WORKPLACES,
    max_age_days: int = 45,  # InHire mantém vaga aberta mais tempo que a Gupy (lá o default é 28)
    check_open: bool = True,
    max_detail: int = 40,
) -> list[JobPosting]:
    """Descobre vagas nos tenants (em paralelo, teto `_MAX_WORKERS`) e devolve JobPosting[]
    deduplicado por jobId, na ordem dos tenants (cyber primeiro).

    Filtros (espelham a Gupy), todos sobre o `detail` já baixado: MODELO (remoto/híbrido),
    RECÊNCIA (≤max_age_days via publishedAt) e ABERTA (status "published" — de graça, sem o
    fetch de HTML que a Gupy faz). Desconhecido/parse falho → mantém (não perde vaga por transiente).
    `workplaces` vazio = sem filtro de modelo; `check_open=False` = não filtra por status.
    """
    if tenants is None:
        # Curated plugin list is the source of truth; INHIRE_TENANTS (.env) EXTENDS it (dedup,
        # order preserved) so a private/extra tenant can be added without editing code. See tenants.py.
        tenants = list(dict.fromkeys([*TENANTS, *settings.inhire_tenants]))
    kws = [k.lower() for k in keywords]
    args = (kws, workplaces, max_age_days, check_open, max_detail)
    if session is not None:
        # Sessão injetada pelo harness → roda sequencial reutilizando-a (respeita config/proxy dela).
        workers = 1
        results = [_scan_tenant(t, *args, session=session) for t in tenants]
    else:
        workers = max(1, min(_MAX_WORKERS, len(tenants)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            # submit na ordem dos tenants; itero na mesma ordem → prioridade preservada no dedup.
            futures = [pool.submit(_scan_tenant, t, *args) for t in tenants]
            results = [fut.result() for fut in futures]

    seen: dict[str, JobPosting] = {}
    dropped_model = dropped_old = closed = 0
    for postings, dm, do, dc in results:
        dropped_model += dm
        dropped_old += do
        closed += dc
        for p in postings:
            seen.setdefault(p.external_id, p)  # 1º tenant a trazer o jobId vence
    log.info(
        "InHire discovery: %d final(is) → -%d modelo → -%d antigas(>%dd) → -%d encerradas, "
        "em %d empresa(s) (%d workers)",
        len(seen), dropped_model, dropped_old, max_age_days, closed, len(tenants), workers,
    )
    return list(seen.values())

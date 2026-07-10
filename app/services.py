"""Serviços de orquestração reutilizáveis (chamados pela UI E pelos scripts — DRY).

Regra: nada de shell-out. A UI chama estas funções direto (mesmo processo), não `subprocess`.
Aqui vive a orquestração que combina IA + PDF + DB; a lógica pura fica em `ai/` e `pdf/`.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from importlib import import_module
from pathlib import Path

from sqlmodel import Session, select

from .ai.tailor import generate
from .config import settings
from .core import audit
from .core.schemas import TailorResult
from .models import Application, Job, Profile
from .pdf.render import render_cv_pdf
from .platforms import REGISTRY
from .web.repo import get_or_create_profile

log = logging.getLogger(__name__)

# Atomic apply claim: job_ids with a submission in flight RIGHT NOW. Both apply entry points
# (single "Candidatar-se" and the batch queue) funnel through `apply_application`, so this
# in-process lock+set is the one gate that prevents two concurrent applies to the same job —
# closing the TOCTOU window that `result == "sent"` alone leaves open (it only commits at the very
# end of the ~30s browser flow). Single-process app → in-process guard is sufficient.
_inflight_lock = threading.Lock()
_inflight: set[int] = set()


def _contact(profile: Profile) -> dict:
    return {
        "full_name": profile.full_name, "email": profile.email, "phone": profile.phone,
        "location": profile.location, "linkedin_url": profile.linkedin_url,
        "portfolio_url": profile.portfolio_url,
    }


# Bloco `application` do manifesto (o que a plataforma consome). Default conservador =
# renderiza PDF + carta, preservando o comportamento antigo p/ plataforma sem o bloco. SPEC §4/§5.
_DEFAULT_APPLICATION = {"cv": "file", "cover_letter": True}


def _application_spec(platform: str) -> dict:
    return {**_DEFAULT_APPLICATION, **REGISTRY.get(platform, {}).get("application", {})}


def tailor_application(
    session: Session, job: Job, profile: Profile | None = None
) -> tuple[Application, TailorResult]:
    """Gera o conteúdo sob medida para `job` e, conforme o manifesto da plataforma, renderiza os
    artefatos (PDF/carta), salva/atualiza a Application e marca a vaga como `tailored`.
    Retorna (Application, TailorResult). Requer LLM_API_KEY.

    O bloco `application` do manifesto decide o que produzir (SPEC §4/§5): `cv: "file"` renderiza o
    PDF; `cv: "onplatform"` (Gupy) só gera o conteúdo (`cv_json`, que alimenta as respostas do
    form_agent) e NÃO renderiza PDF. Idempotente por vaga: regenera e sobrescreve os arquivos.
    """
    profile = profile or get_or_create_profile(session)
    spec = _application_spec(job.platform)
    result = generate(profile.to_master_cv(), {
        "title": job.title, "company": job.company,
        "location": job.location, "description": job.description,
    })

    settings.ensure_dirs()
    app_row = session.exec(
        select(Application).where(Application.job_id == job.id)
    ).first() or Application(job_id=job.id)

    # PDF só quando a plataforma exige arquivo. "onplatform" fica sem cv_pdf_path (o gate de
    # candidatura passa a checar cv_json, não o PDF — ver apply_application).
    if spec["cv"] == "file":
        cv_pdf = settings.generated_dir / f"cv_job_{job.id}.pdf"
        render_cv_pdf(_contact(profile), result, cv_pdf)
        app_row.cv_pdf_path = str(cv_pdf)
    else:
        app_row.cv_pdf_path = ""

    if spec["cover_letter"]:
        cover_txt = settings.generated_dir / f"cover_job_{job.id}.txt"
        cover_txt.write_text(result.cover_letter, encoding="utf-8")
        app_row.cover_letter_path = str(cover_txt)
    else:
        app_row.cover_letter_path = ""

    app_row.cv_json = result.cv.model_dump()
    app_row.language = result.language
    session.add(app_row)
    job.status = "tailored"
    session.add(job)
    session.commit()
    session.refresh(app_row)
    return app_row, result


def discover_and_rank(
    session: Session, platform: str, keywords: list[str], profile: Profile | None = None
) -> dict:
    """Descobre vagas na plataforma, descarta afirmativas inelegíveis, salva e ranqueia as novas.
    Mesmo pipeline do `scripts/discover_rank.py`, chamável pela UI. Retorna estatísticas.
    Só ranqueia vagas com score ausente (as já ranqueadas são puladas → buscas repetidas são rápidas).
    """
    from .ai.eligibility import filter_eligible
    from .ai.ranker import rank_job
    from .web.repo import save_postings

    discover = import_module(f"app.platforms.{platform}.discovery").discover
    postings = discover(keywords)
    found = len(postings)

    profile = profile or get_or_create_profile(session)
    postings, discarded = filter_eligible(postings, profile.demographics())
    saved = save_postings(session, postings)

    cv = profile.to_master_cv()
    ranked = 0
    for j in saved:
        if j.score is not None or j.hidden:  # já ranqueada, ou oculta pelo usuário → pula
            continue
        try:
            r = rank_job(cv, {"title": j.title, "company": j.company,
                              "location": j.location, "description": j.description})
            j.score, j.score_reason, j.status = r.score, r.reason, "ranked"
            session.add(j)
            session.commit()
            ranked += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("rank falhou (%s): %s", j.title, exc)
    return {"found": found, "discarded": len(discarded), "ranked": ranked, "kept": len(saved)}


def batch_tailor(session: Session, min_score: int = 0) -> dict:
    """Gera CV+carta em lote para todas as vagas com score >= `min_score` que AINDA NÃO têm CV.
    Pula as já geradas (Application com cv_pdf_path). Síncrono — pode demorar (uma chamada de LLM por vaga).
    """
    from .web.repo import jobs_by_score

    with_cv = {
        a.job_id for a in session.exec(select(Application)).all() if a.cv_pdf_path
    }
    profile = get_or_create_profile(session)
    targets = [
        j for j in jobs_by_score(session)
        if j.score is not None and j.score >= min_score and j.id not in with_cv
    ]
    generated = failed = 0
    for job in targets:
        try:
            tailor_application(session, job, profile)
            generated += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            log.warning("batch_tailor falhou (%s): %s", job.title, exc)
    return {"candidates": len(targets), "generated": generated, "failed": failed,
            "min_score": min_score}


def apply_application(
    session: Session, job: Job, *, allow_real: bool | None = None, headless: bool = False
) -> dict:
    """Candidata-se à vaga via o fluxo automático do plugin (canal browser), no MESMO processo —
    sem shell-out. Abre o BrowserHarness, roda `run_auto_apply`, fecha e registra o resultado.

    Gating: pela UI, `allow_real` NÃO depende de ALLOW_REAL_SUBMIT — é **True por padrão**
    (candidatura é produção). A autorização vem do diálogo "deseja continuar?" da UI (hx-confirm)
    antes de disparar; por isso `confirm` interno é sempre True. O flag ALLOW_REAL_SUBMIT segue
    valendo só para o CLI (`scripts/auto_apply.py`). Requer sessão logada.
    Retorna o dict de resultado do plugin ({outcome, message, ...}).
    """
    from .core.browser import BrowserHarness
    from .core.session import has_session

    app_row = session.exec(select(Application).where(Application.job_id == job.id)).first()
    # Gate = conteúdo gerado (cv_json), não o PDF: plataformas "onplatform" (Gupy) não têm PDF.
    if app_row is None or not app_row.cv_json:
        return {"outcome": "error", "message": "Gere o CV/carta antes de candidatar-se."}
    # Idempotência: já enviada → NÃO reabre o browser (evita duplo-envio irreversível e sobe
    # Chromium à toa). `result == "sent"` só é gravado após confirmação real da Gupy (_finalized_ok
    # no apply.py; falso positivo foi eliminado na saga A–G). O caso inverso — DB diz não-enviada
    # mas a plataforma já concluiu — é coberto pelo plugin, que retorna 'already_applied' e corrige.
    if app_row.result in ("sent", "not_advanced"):
        return {"outcome": "already_applied",
                "message": "Candidatura já finalizada anteriormente (não reabri o navegador)."}
    if not has_session(job.platform):
        return {"outcome": "error",
                "message": f"Sem sessão '{job.platform}'. Rode: python scripts/login.py {job.platform}"}
    mod = import_module(f"app.platforms.{job.platform}.apply")
    run_auto_apply = getattr(mod, "run_auto_apply", None)
    if run_auto_apply is None:
        return {"outcome": "error",
                "message": f"Plataforma '{job.platform}' ainda não tem candidatura automática."}

    # Atomically claim this job before opening the browser. If a rival apply already holds it,
    # bail immediately (do NOT open a second browser / re-submit). The claim is released in the
    # finally below, only after the winner has committed its result.
    with _inflight_lock:
        if job.id in _inflight:
            return {"outcome": "in_progress",
                    "message": "Já existe uma candidatura em andamento para esta vaga."}
        _inflight.add(job.id)
    try:
        # Re-check under the claim: a rival may have finished + committed "sent" in the window
        # between our earlier read and winning the claim. refresh() re-reads from the DB (the rival
        # ran in a different session), so a stale not-sent value can't slip a duplicate through.
        session.refresh(app_row)
        if app_row.result == "sent":
            return {"outcome": "already_applied",
                    "message": "Candidatura já enviada anteriormente (não reabri o navegador)."}

        profile = get_or_create_profile(session)
        cover = ""
        if app_row.cover_letter_path and Path(app_row.cover_letter_path).exists():
            cover = Path(app_row.cover_letter_path).read_text(encoding="utf-8")
        # UI = produção: envio real por padrão (não usa ALLOW_REAL_SUBMIT). O diálogo da UI é a trava.
        allow_real = True if allow_real is None else allow_real

        with BrowserHarness(headless=headless) as h:
            ctx = h.new_context(job.platform)
            page = ctx.new_page()
            try:
                result = run_auto_apply(
                    page, job=job, application=app_row, master_cv=profile.to_master_cv(),
                    extras=profile.to_application_extras(), cover=cover,
                    allow_real=allow_real, confirm=lambda _prompt: True, log_fn=log.info,
                )
            finally:
                try:
                    ctx.close()
                except Exception:  # noqa: BLE001
                    pass

        outcome = result.get("outcome")
        if outcome in ("sent", "already_applied"):
            app_row.result, app_row.submitted_at, job.status = "sent", datetime.utcnow(), "applied"
        elif outcome == "not_advanced":
            # enviada, mas reprovada em pergunta eliminatória: É um envio (não erro) → registra
            # submitted_at + status applied, com result distinto p/ o funil enxergar a eliminação.
            app_row.result, app_row.submitted_at, job.status = \
                "not_advanced", datetime.utcnow(), "applied"
            app_row.error = ""
        elif outcome == "needs_review":
            job.status = "pending_approval"
        elif outcome == "dry_run":
            app_row.result = "dry_run"
        elif outcome == "error":
            app_row.result, app_row.error = "error", result.get("message", "")
        # Persist the AI's Q&A whenever the form flow actually ran (any outcome), for user review.
        if result.get("qa"):
            app_row.form_qa = result["qa"]
        session.add(app_row)
        session.add(job)
        audit.log(session, "auto_apply", platform=job.platform, job_id=job.id,
                  detail={"outcome": outcome, "message": result.get("message", ""), "via": "ui"})
        session.commit()
        return result
    finally:
        with _inflight_lock:
            _inflight.discard(job.id)

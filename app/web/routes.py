"""Rotas do dashboard (Fase 1: Profile). HTMX + Jinja2."""
from __future__ import annotations

from datetime import datetime
from importlib import import_module
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .. import applyqueue, bgtasks
from ..config import settings
from ..core import audit
from ..db import engine, get_session
from ..models import Application, Job
from ..services import apply_application, batch_tailor, discover_and_rank, tailor_application
from .repo import get_or_create_profile, jobs_by_score

# Long UI operations run in the background (bgtasks) so the request never blocks for minutes.
# Labels shown by the polling fragment while each task runs.
_BG_LABELS = {
    "search": "⏳ Descobrindo + ranqueando vagas… (pode levar alguns minutos)",
    "tailor": "⏳ Gerando CVs em lote… (uma chamada de IA por vaga)",
}


def _run_search(keywords: str) -> dict:
    """Background body of /jobs/search — opens its own Session (worker thread)."""
    with Session(engine) as s:
        profile = get_or_create_profile(s)
        kws = [k.strip() for k in keywords.split(",") if k.strip()] \
            or profile.target_roles or ["segurança da informação"]
        return discover_and_rank(s, "gupy", kws, profile)


def _run_tailor(min_score: int) -> dict:
    """Background body of /jobs/tailor-all — opens its own Session (worker thread)."""
    with Session(engine) as s:
        return batch_tailor(s, min_score)


def _apply_module(platform: str):
    return import_module(f"app.platforms.{platform}.apply")


def _application_for(session: Session, job_id: int) -> Application | None:
    return session.exec(select(Application).where(Application.job_id == job_id)).first()

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def index() -> RedirectResponse:
    return RedirectResponse(url="/profile")


@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    profile = get_or_create_profile(session)
    return templates.TemplateResponse(request, "profile.html", {"p": profile})


@router.post("/profile", response_class=HTMLResponse)
def profile_save(
    request: Request,
    session: Session = Depends(get_session),
    full_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    location: str = Form(""),
    linkedin_url: str = Form(""),
    portfolio_url: str = Form(""),
    seniority: str = Form("junior"),
    summary: str = Form(""),
    target_roles: str = Form(""),
    skills: str = Form(""),
    soft_skills: str = Form(""),
    # preferências de candidatura (respostas recorrentes de formulário — EXTRAS do form_agent)
    salary_expectation: str = Form(""),
    availability: str = Form(""),
    work_model: str = Form(""),
    pcd: str = Form(""),
    race: str = Form(""),
    gender: str = Form(""),
    rg: str = Form(""),
    cpf: str = Form(""),
    job_source: str = Form(""),
    notice_period: str = Form(""),
    faq: str = Form(""),
) -> HTMLResponse:
    profile = get_or_create_profile(session)
    profile.full_name = full_name
    profile.email = email
    profile.phone = phone
    profile.location = location
    profile.linkedin_url = linkedin_url
    profile.portfolio_url = portfolio_url
    profile.seniority = seniority
    profile.summary = summary
    # campos de lista: uma linha por item
    profile.target_roles = [x.strip() for x in target_roles.splitlines() if x.strip()]
    profile.skills = [x.strip() for x in skills.splitlines() if x.strip()]
    profile.soft_skills = [x.strip() for x in soft_skills.splitlines() if x.strip()]
    # FAQ livre: uma "pergunta :: resposta" por linha
    faq_map: dict[str, str] = {}
    for line in faq.splitlines():
        if "::" in line:
            q, a = line.split("::", 1)
            if q.strip() and a.strip():
                faq_map[q.strip()] = a.strip()
    profile.application_prefs = {
        "salary_expectation": salary_expectation.strip(),
        "availability": availability.strip(),
        "work_model": work_model.strip(),
        "pcd": pcd.strip(),
        "race": race.strip(),
        "gender": gender.strip(),
        "rg": rg.strip(),
        "cpf": cpf.strip(),
        "job_source": job_source.strip(),
        "notice_period": notice_period.strip(),
        "faq": faq_map,
    }
    profile.updated_at = datetime.utcnow()
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return templates.TemplateResponse(request, "_saved.html", {"p": profile})


@router.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    jobs = jobs_by_score(session)
    apps = {a.job_id: a for a in session.exec(select(Application)).all()}
    profile = get_or_create_profile(session)
    default_kw = ", ".join(profile.target_roles) if profile.target_roles else \
        "pentest, appsec, red team, segurança da informação"
    return templates.TemplateResponse(
        request, "jobs.html",
        {"jobs": jobs, "apps": apps, "allow_real": settings.allow_real_submit,
         "default_keywords": default_kw},
    )


@router.post("/jobs/search", response_class=HTMLResponse)
def jobs_search(request: Request, keywords: str = Form("")) -> HTMLResponse:
    """Dispara descoberta + ranqueio em BACKGROUND (não trava a request) e devolve um fragmento
    que faz polling do progresso. Reusa o padrão da fila de candidatura (bgtasks)."""
    bgtasks.start("search", lambda: _run_search(keywords))
    return templates.TemplateResponse(
        request, "_bg_running.html", {"task": "search", "label": _BG_LABELS["search"]})


@router.post("/jobs/tailor-all", response_class=HTMLResponse)
def jobs_tailor_all(request: Request, min_score: int = Form(0)) -> HTMLResponse:
    """Dispara a geração de CV em lote em BACKGROUND e devolve o fragmento de polling.
    Antes travava a request por minutos (uma chamada de IA por vaga)."""
    bgtasks.start("tailor", lambda: _run_tailor(min_score))
    return templates.TemplateResponse(
        request, "_bg_running.html", {"task": "tailor", "label": _BG_LABELS["tailor"]})


@router.get("/jobs/bg-status", response_class=HTMLResponse)
def jobs_bg_status(request: Request, task: str,
                   session: Session = Depends(get_session)) -> HTMLResponse:
    """Polling de uma tarefa longa (search|tailor). Enquanto ativa, devolve o mesmo fragmento
    (o poll continua); ao terminar, devolve a lista de vagas com as estatísticas da tarefa —
    substituindo o spinner (hx-swap=outerHTML) e encerrando o polling."""
    st = bgtasks.get(task)
    if st and st["state"] in bgtasks.ACTIVE:
        return templates.TemplateResponse(
            request, "_bg_running.html",
            {"task": task, "label": _BG_LABELS.get(task, "⏳ processando…")})
    ctx: dict = {"allow_real": settings.allow_real_submit}
    if st and st["state"] == "failed":
        ctx["search_error"] = st["message"]
    elif st and st["state"] == "done":
        ctx["search_stats" if task == "search" else "batch_stats"] = st.get("result") or {}
    ctx["jobs"] = jobs_by_score(session)
    ctx["apps"] = {a.job_id: a for a in session.exec(select(Application)).all()}
    return templates.TemplateResponse(request, "_job_list.html", ctx)


@router.post("/jobs/{job_id}/tailor", response_class=HTMLResponse)
def job_tailor(job_id: int, request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """Gera CV+carta sob medida via serviço (mesmo processo — sem shell-out). Devolve o bloco
    de ações atualizado (HTMX). O job_id vem tipado do path, sem superfície de injeção."""
    job = session.get(Job, job_id)
    if job is None:
        return HTMLResponse('<span class="hint">Vaga não encontrada.</span>', status_code=404)
    try:
        app_row, _ = tailor_application(session, job)
    except Exception as exc:  # noqa: BLE001 — feedback amigável na UI
        return HTMLResponse(
            f'<span class="hint">Falha ao gerar (verifique LLM_API_KEY): {exc}</span>'
        )
    audit.log(session, "tailor", platform=job.platform, job_id=job.id,
              detail={"language": app_row.language})
    return templates.TemplateResponse(
        request, "_job_actions.html",
        {"j": job, "a": app_row, "allow_real": settings.allow_real_submit},
    )


@router.post("/jobs/{job_id}/apply", response_class=HTMLResponse)
def job_apply(job_id: int, request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """Candidata-se via serviço (mesmo processo, abre o navegador logado). Sem shell-out.
    Gated por ALLOW_REAL_SUBMIT; a UI confirma envio real com hx-confirm antes de disparar."""
    job = session.get(Job, job_id)
    if job is None:
        return HTMLResponse('<span class="hint">Vaga não encontrada.</span>', status_code=404)
    try:
        result = apply_application(session, job)
    except Exception as exc:  # noqa: BLE001 — feedback amigável na UI
        return HTMLResponse(f'<span class="hint">❌ Falha ao candidatar: {exc}</span>')
    icon = {"sent": "✅", "dry_run": "🟡", "needs_review": "⛔",
            "cancelled": "✋", "error": "❌"}.get(result.get("outcome"), "•")
    return HTMLResponse(f'<span class="hint">{icon} {result.get("message", "")}</span>')


@router.get("/jobs/{job_id}/cv.pdf")
def job_cv_pdf(job_id: int, session: Session = Depends(get_session)):
    app_row = session.exec(select(Application).where(Application.job_id == job_id)).first()
    if not app_row or not app_row.cv_pdf_path or not Path(app_row.cv_pdf_path).exists():
        return HTMLResponse("CV ainda não gerado para esta vaga.", status_code=404)
    return FileResponse(app_row.cv_pdf_path, media_type="application/pdf",
                        filename=f"cv_job_{job_id}.pdf")


@router.get("/jobs/{job_id}/cover", response_class=HTMLResponse)
def job_cover(job_id: int, request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    app_row = session.exec(select(Application).where(Application.job_id == job_id)).first()
    if not app_row or not app_row.cover_letter_path or not Path(app_row.cover_letter_path).exists():
        return HTMLResponse('<span class="hint">Carta ainda não gerada.</span>')
    text = Path(app_row.cover_letter_path).read_text(encoding="utf-8")
    return HTMLResponse(f'<div style="white-space:pre-wrap; margin-top:8px">{text}</div>')


@router.get("/jobs/{job_id}/questions", response_class=HTMLResponse)
def job_questions(job_id: int, request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """Inline fragment with the AI's screening-form Q&A for this application (expands like the
    cover letter). Shows every question and what was answered / left unanswered."""
    app_row = session.exec(select(Application).where(Application.job_id == job_id)).first()
    if not app_row or not app_row.form_qa:
        return HTMLResponse('<span class="hint">Sem perguntas registradas para esta candidatura.</span>')
    return templates.TemplateResponse(request, "_questions.html", {"qa": app_row.form_qa})


def _batch_ctx(session: Session, enqueued: int | None = None) -> dict:
    """Contexto do painel de candidatura em lote (status da fila em memória)."""
    snap = applyqueue.snapshot()
    titles = {j.id: j.title for j in session.exec(select(Job)).all()}
    order = {"running": 0, "queued": 1, "done": 2, "failed": 3}
    rows = [{"job_id": jid, "title": titles.get(jid, "?"), **st} for jid, st in snap.items()]
    rows.sort(key=lambda r: order.get(r.get("state"), 9))
    return {"counts": applyqueue.counts(), "rows": rows,
            "active": applyqueue.is_active(), "enqueued": enqueued}


@router.get("/queue", response_class=HTMLResponse)
def queue_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    apps = session.exec(select(Application)).all()
    jobs = {j.id: j for j in session.exec(select(Job)).all()}
    items = [(jobs[a.job_id], a) for a in apps if a.job_id in jobs]
    items.sort(key=lambda t: (t[0].score or 0), reverse=True)
    ctx = {"items": items, "allow_real": settings.allow_real_submit}
    ctx.update(_batch_ctx(session))
    return templates.TemplateResponse(request, "queue.html", ctx)


@router.post("/queue/apply-all", response_class=HTMLResponse)
def queue_apply_all(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """Enfileira candidatura para TODAS as vagas com CV gerado ainda não enviadas (máx. 5 por vez)."""
    apps = session.exec(select(Application)).all()
    jobs = {j.id: j for j in session.exec(select(Job)).all()}
    eligible = [a.job_id for a in apps
                if a.cv_pdf_path and a.job_id in jobs and jobs[a.job_id].status != "applied"]
    enq = sum(1 for jid in eligible if applyqueue.enqueue(jid))
    return templates.TemplateResponse(request, "_batch_status.html", _batch_ctx(session, enqueued=enq))


@router.get("/queue/apply-status", response_class=HTMLResponse)
def queue_apply_status(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """Polling do status da fila de candidatura em lote."""
    return templates.TemplateResponse(request, "_batch_status.html", _batch_ctx(session))


@router.post("/jobs/{job_id}/prepare", response_class=HTMLResponse)
def job_prepare(job_id: int, session: Session = Depends(get_session)) -> HTMLResponse:
    job = session.get(Job, job_id)
    app_row = _application_for(session, job_id)
    result = _apply_module(job.platform).prepare(job, app_row)
    if result.ok and job.status == "tailored":
        job.status = "pending_approval"
        session.add(job)
    audit.log(session, "prepare", platform=job.platform, job_id=job_id,
              detail={"message": result.message})
    return HTMLResponse(f'<span class="hint">{result.message}</span>')


@router.post("/jobs/{job_id}/approve", response_class=HTMLResponse)
def job_approve(job_id: int, session: Session = Depends(get_session)) -> HTMLResponse:
    job = session.get(Job, job_id)
    app_row = _application_for(session, job_id)
    result = _apply_module(job.platform).submit(job, app_row, allow_real=settings.allow_real_submit)
    if result.submitted:
        app_row.result, app_row.submitted_at, job.status = "sent", datetime.utcnow(), "applied"
    else:
        app_row.result = "dry_run" if result.ok else "error"
        app_row.error = "" if result.ok else result.message
        job.status = "approved" if result.ok else job.status
    session.add(app_row)
    session.add(job)
    audit.log(session, "submit", platform=job.platform, job_id=job_id,
              detail={"message": result.message, "submitted": result.submitted})
    return HTMLResponse(f'<span class="hint">{result.message}</span>')


@router.post("/jobs/{job_id}/reject", response_class=HTMLResponse)
def job_reject(job_id: int, session: Session = Depends(get_session)) -> HTMLResponse:
    job = session.get(Job, job_id)
    job.status = "rejected"
    session.add(job)
    audit.log(session, "reject", platform=job.platform, job_id=job_id)
    return HTMLResponse('<span class="hint">Vaga rejeitada.</span>')


@router.post("/profile/suggest-seniority", response_class=HTMLResponse)
def suggest_seniority(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """IA sugere a senioridade a partir do master_cv (usuário confirma salvando)."""
    profile = get_or_create_profile(session)
    try:
        from ..ai.llm_client import derive_seniority

        result = derive_seniority(profile.to_master_cv())
        msg = f"Sugestão: {result.seniority} — {result.reason}"
    except Exception as exc:  # noqa: BLE001 — feedback amigável na UI
        msg = f"Não foi possível sugerir (verifique LLM_API_KEY): {exc}"
    return HTMLResponse(f'<span class="hint">{msg}</span>')

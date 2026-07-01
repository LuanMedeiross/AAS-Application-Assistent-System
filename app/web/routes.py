"""Rotas do dashboard (Fase 1: Profile). HTMX + Jinja2."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from ..db import get_session
from ..models import Application
from .repo import get_or_create_profile, jobs_by_score

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
    profile.updated_at = datetime.utcnow()
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return templates.TemplateResponse(request, "_saved.html", {"p": profile})


@router.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    jobs = jobs_by_score(session)
    apps = {a.job_id: a for a in session.exec(select(Application)).all()}
    return templates.TemplateResponse(request, "jobs.html", {"jobs": jobs, "apps": apps})


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


@router.post("/profile/suggest-seniority", response_class=HTMLResponse)
def suggest_seniority(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """IA sugere a senioridade a partir do master_cv (usuário confirma salvando)."""
    profile = get_or_create_profile(session)
    try:
        from ..ai.deepseek import derive_seniority

        result = derive_seniority(profile.to_master_cv())
        msg = f"Sugestão: {result.seniority} — {result.reason}"
    except Exception as exc:  # noqa: BLE001 — feedback amigável na UI
        msg = f"Não foi possível sugerir (verifique DEEPSEEK_API_KEY): {exc}"
    return HTMLResponse(f'<span class="hint">{msg}</span>')

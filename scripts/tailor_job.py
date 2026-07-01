"""Gera CV + carta sob medida para uma vaga, renderiza o PDF e registra a Application.

Uso: python scripts/tailor_job.py [job_id]
Sem job_id, usa a vaga de maior score. Requer DEEPSEEK_API_KEY no .env.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session, select  # noqa: E402

from app.ai.tailor import generate  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import Application, Job  # noqa: E402
from app.pdf.render import render_cv_pdf  # noqa: E402
from app.web.repo import get_or_create_profile, jobs_by_score  # noqa: E402


def _contact(profile) -> dict:
    return {
        "full_name": profile.full_name, "email": profile.email, "phone": profile.phone,
        "location": profile.location, "linkedin_url": profile.linkedin_url,
        "portfolio_url": profile.portfolio_url,
    }


def main() -> None:
    init_db()
    with Session(engine) as s:
        if len(sys.argv) > 1:
            job = s.get(Job, int(sys.argv[1]))
        else:
            ranked = [j for j in jobs_by_score(s) if j.score is not None]
            job = ranked[0] if ranked else None
        if job is None:
            raise SystemExit("Nenhuma vaga encontrada. Rode discover_rank.py antes.")

        profile = get_or_create_profile(s)
        print(f"Gerando CV/carta para: [{job.score}] {job.title} @ {job.company}")
        result = generate(profile.to_master_cv(), {
            "title": job.title, "company": job.company,
            "location": job.location, "description": job.description,
        })
        print(f"  idioma detectado: {result.language} | skills no CV: {len(result.cv.skills)} "
              f"| carta: {len(result.cover_letter.split())} palavras")

        cv_pdf = settings.generated_dir / f"cv_job_{job.id}.pdf"
        render_cv_pdf(_contact(profile), result, cv_pdf)
        cover_txt = settings.generated_dir / f"cover_job_{job.id}.txt"
        cover_txt.write_text(result.cover_letter, encoding="utf-8")

        app_row = s.exec(select(Application).where(Application.job_id == job.id)).first() or Application(job_id=job.id)
        app_row.cv_pdf_path = str(cv_pdf)
        app_row.cover_letter_path = str(cover_txt)
        app_row.cv_json = result.cv.model_dump()
        app_row.language = result.language
        s.add(app_row)
        job.status = "tailored"
        s.add(job)
        s.commit()

        print(f"  CV PDF:  {cv_pdf} ({cv_pdf.stat().st_size} bytes)")
        print(f"  Carta:   {cover_txt}")
        print("\n--- Carta (preview) ---")
        print(result.cover_letter)


if __name__ == "__main__":
    main()

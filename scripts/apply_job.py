"""Envio ASSISTIDO/SUPERVISIONADO de uma candidatura (canal browser).

Abre a página da vaga JÁ LOGADA (sessão salva), mostra o CV/carta gerados, e deixa VOCÊ
concluir e enviar na janela — nada de auto-submit cego. Ao terminar, registra a candidatura.

Uso: python scripts/apply_job.py <job_id>
Pré-requisito: python scripts/login.py gupy  (sessão salva).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session, select  # noqa: E402

from app.core import audit  # noqa: E402
from app.core.browser import BrowserHarness  # noqa: E402
from app.core.session import has_session  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import Application, Job  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Uso: python scripts/apply_job.py <job_id>")
    job_id = int(sys.argv[1])

    init_db()
    with Session(engine) as s:
        job = s.get(Job, job_id)
        if job is None:
            raise SystemExit(f"Vaga {job_id} não encontrada.")
        app_row = s.exec(select(Application).where(Application.job_id == job_id)).first()
        if app_row is None or not app_row.cv_pdf_path:
            raise SystemExit("CV/carta não gerados. Rode: python scripts/tailor_job.py " + str(job_id))
        if not has_session(job.platform):
            raise SystemExit(f"Sem sessão '{job.platform}'. Rode: python scripts/login.py {job.platform}")

        print(f"Vaga: {job.title} @ {job.company}\nURL: {job.url}")
        print(f"CV (para upload): {app_row.cv_pdf_path}")
        print(f"Carta (para colar):\n{Path(app_row.cover_letter_path).read_text(encoding='utf-8')}\n")

        with BrowserHarness(headless=False) as h:
            ctx = h.new_context(job.platform)
            page = ctx.new_page()
            page.goto(job.url)
            print("Página aberta LOGADA. Revise, anexe o CV, cole a carta e ENVIE você mesmo.")
            resp = input("Enviou a candidatura? [s/N] ").strip().lower()
            ctx.close()

        if resp == "s":
            app_row.result = "sent"
            app_row.submitted_at = datetime.utcnow()
            job.status = "applied"
            audit.log(s, "submit", platform=job.platform, job_id=job.id,
                      detail={"mode": "assisted", "url": job.url})
        else:
            app_row.result = "skipped"
            job.status = "approved"
            audit.log(s, "submit_skipped", platform=job.platform, job_id=job.id)
        s.add(app_row)
        s.add(job)
        s.commit()
        print(f"Registrado: job.status={job.status} | application.result={app_row.result}")


if __name__ == "__main__":
    main()

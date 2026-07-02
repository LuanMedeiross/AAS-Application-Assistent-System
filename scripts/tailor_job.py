"""Gera CV + carta sob medida para uma vaga, renderiza o PDF e registra a Application.

Uso: python scripts/tailor_job.py [job_id]
Sem job_id, usa a vaga de maior score. Requer LLM_API_KEY no .env.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session  # noqa: E402

from app.db import engine, init_db  # noqa: E402
from app.models import Job  # noqa: E402
from app.services import tailor_application  # noqa: E402
from app.web.repo import jobs_by_score  # noqa: E402


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

        print(f"Gerando CV/carta para: [{job.score}] {job.title} @ {job.company}")
        app_row, result = tailor_application(s, job)
        print(f"  idioma detectado: {result.language} | skills no CV: {len(result.cv.skills)} "
              f"| carta: {len(result.cover_letter.split())} palavras")
        print(f"  CV PDF:  {app_row.cv_pdf_path}")
        print(f"  Carta:   {app_row.cover_letter_path}")
        print("\n--- Carta (preview) ---")
        print(result.cover_letter)


if __name__ == "__main__":
    main()

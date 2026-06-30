"""Importa o Profile a partir do export oficial de dados do LinkedIn (ZIP ou diretório).

Uso: python scripts/import_linkedin.py "C:/caminho/Basic_LinkedInDataExport_xxx.zip"
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session  # noqa: E402

from app.db import engine, init_db  # noqa: E402
from app.linkedin.parser import parse_linkedin_export  # noqa: E402
from app.web.repo import apply_master_cv, get_or_create_profile  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Informe o caminho do export do LinkedIn (.zip ou diretório).")
    cv = parse_linkedin_export(sys.argv[1])

    init_db()
    with Session(engine) as session:
        profile = get_or_create_profile(session)
        apply_master_cv(profile, cv)
        session.add(profile)
        session.commit()
        session.refresh(profile)
        print(f"Importado do LinkedIn: {profile.full_name}")
        print(f"  experiências: {len(profile.experiences)} | skills: {len(profile.skills)}")
        print("Revise/edite no dashboard (/profile) antes de usar.")


if __name__ == "__main__":
    main()

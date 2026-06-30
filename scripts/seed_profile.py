"""Popula o Profile a partir de curriculum/master_cv.json.

Uso: python scripts/seed_profile.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session  # noqa: E402

from app.db import engine, init_db  # noqa: E402
from app.web.repo import apply_master_cv, get_or_create_profile  # noqa: E402


def main() -> None:
    cv_path = ROOT / "curriculum" / "master_cv.json"
    if not cv_path.exists():
        raise SystemExit(f"Arquivo não encontrado: {cv_path}")
    cv = json.loads(cv_path.read_text(encoding="utf-8"))

    init_db()
    with Session(engine) as session:
        profile = get_or_create_profile(session)
        apply_master_cv(profile, cv)
        session.add(profile)
        session.commit()
        session.refresh(profile)
        print(f"Profile populado: {profile.full_name} ({profile.seniority})")
        print(f"  experiências: {len(profile.experiences)} | skills: {len(profile.skills)} "
              f"| certs: {len(profile.certifications)}")


if __name__ == "__main__":
    main()

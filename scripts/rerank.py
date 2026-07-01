"""Re-ranqueia TODAS as vagas do banco com o ranker atual (modelo + rubrica vigentes).

Diferente do discover_rank (que só ranqueia vagas novas, score=None), este re-pontua tudo —
útil ao mudar o modelo/rubrica de ranking. Não descobre nem envia nada.

Uso: python scripts/rerank.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session, select  # noqa: E402

from app.ai.ranker import rank_job  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import Job  # noqa: E402
from app.web.repo import get_or_create_profile  # noqa: E402


def main() -> None:
    init_db()
    print(f"Re-ranqueando com model_rank={settings.model_rank}")
    with Session(engine) as s:
        cv = get_or_create_profile(s).to_master_cv()
        jobs = s.exec(select(Job)).all()
        print(f"{len(jobs)} vaga(s) no banco.\n")
        for j in jobs:
            try:
                r = rank_job(cv, {"title": j.title, "company": j.company,
                                  "location": j.location, "description": j.description})
                j.score, j.score_reason, j.status = r.score, r.reason, "ranked"
                s.add(j); s.commit()
                print(f"  [{r.score:3}] {j.title[:50]:50} | {j.company[:22]}")
            except Exception as exc:  # noqa: BLE001
                print(f"  [erro] {j.title[:50]}: {exc}")

        print("\n=== TOP 15 (novo ranking) ===")
        top = s.exec(select(Job).order_by(Job.score.desc())).all()[:15]
        for j in top:
            print(f"[{j.score:3}] {j.title[:48]:48} | {j.company[:20]:20} | {j.location[:14]}")


if __name__ == "__main__":
    main()

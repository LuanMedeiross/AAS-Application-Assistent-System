"""Reconcilia o banco com a realidade: REMOVE vagas Gupy vencidas (>28d), ENCERRADAS, ou
AFIRMATIVAS exclusivas a grupos aos quais o candidato não pertence (fator imutável).

Preserva o histórico: vagas já aplicadas (status "applied" ou com Application result="sent")
NUNCA são removidas, mesmo que agora estejam fechadas.

Uso: python scripts/cleanup_jobs.py [--dry-run]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session, select  # noqa: E402

from app.ai.eligibility import _has_trigger, classify_affirmative, is_ineligible  # noqa: E402
from app.core.http_client import new_session  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import Application, Job  # noqa: E402
from app.platforms.gupy.discovery import _is_open, _is_recent  # noqa: E402
from app.web.repo import get_or_create_profile  # noqa: E402

MAX_AGE_DAYS = 28


def main() -> None:
    dry = "--dry-run" in sys.argv
    init_db()
    http = new_session()
    removed = kept_applied = kept_ok = 0
    with Session(engine) as s:
        demo = get_or_create_profile(s).demographics()
        jobs = s.exec(select(Job).where(Job.platform == "gupy")).all()
        sent_job_ids = {
            a.job_id for a in s.exec(select(Application)).all() if a.result == "sent"
        }
        print(f"{len(jobs)} vaga(s) Gupy no banco. Verificando recência + aberta + afirmativa...")
        print(f"Autoidentificação: {demo}\n")
        for j in jobs:
            if j.status == "applied" or j.id in sent_job_ids:
                kept_applied += 1
                continue
            recent = _is_recent(j.raw or {}, MAX_AGE_DAYS)
            open_ = _is_open(http, j.url) if recent else False
            motivo = None
            if not recent:
                motivo = "antiga (>28d)"
            elif not open_:
                motivo = "encerrada"
            elif _has_trigger(f"{j.title} {j.description}".lower()):
                res = classify_affirmative(j.title, j.description)
                if is_ineligible(res, demo):
                    motivo = f"afirmativa {res.grupos}"
            if motivo is None:
                kept_ok += 1
                continue
            print(f"  {'[dry] ' if dry else ''}remover [{j.score if j.score is not None else '-'}] "
                  f"{j.title[:45]:45} | {j.company[:18]:18} | {motivo}")
            if not dry:
                for a in s.exec(select(Application).where(Application.job_id == j.id)).all():
                    s.delete(a)
                s.delete(j)
                removed += 1
        if not dry:
            s.commit()
        print(f"\nResumo: removidas={removed} | preservadas(aplicadas)={kept_applied} | "
              f"mantidas(ok)={kept_ok}")

        if not dry:
            print("\n=== TOP 12 (banco limpo) ===")
            for j in s.exec(select(Job).order_by(Job.score.desc())).all()[:12]:
                sc = j.score if j.score is not None else "-"
                print(f"[{sc:>3}] {j.title[:46]:46} | {j.company[:20]:20} | {j.location[:14]}")


if __name__ == "__main__":
    main()

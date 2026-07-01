"""Reconcilia as candidaturas marcadas 'applied' que podem ser FALSO POSITIVO (iniciadas mas
não finalizadas). Re-roda o apply (agora com verificação de confirmação) em cada uma:

  - já finalizada de verdade  -> outcome 'already_applied' (não re-submete; detecção de 'done')
  - iniciada e não finalizada -> completa e VERIFICA a confirmação -> 'sent'
  - não confirmou             -> 'error' (status volta a ser retentável, NÃO enviada)

Roda headless. Uso:
    python scripts/reconcile_applied.py [--dry-run] [--threads N]
- --dry-run : só lista o que faria (não abre navegador).
- --threads N : quantas candidaturas em paralelo (default 1). Cada thread = 1 navegador.
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session, select  # noqa: E402

from app.db import engine, init_db  # noqa: E402
from app.models import Application, Job  # noqa: E402
from app.services import apply_application  # noqa: E402

MAX_THREADS = 5  # teto de segurança (navegadores simultâneos)


def _arg_int(flag: str, default: int) -> int:
    if flag in sys.argv:
        try:
            return int(sys.argv[sys.argv.index(flag) + 1])
        except (ValueError, IndexError):
            pass
    return default


def _reconcile_one(job_id: int) -> tuple[int, str, dict]:
    """Reconcilia UMA vaga em sua própria Session/navegador (thread-safe)."""
    with Session(engine) as s:
        job = s.get(Job, job_id)
        app_row = s.exec(select(Application).where(Application.job_id == job_id)).first()
        # zera o status para o serviço re-rodar e re-verificar (idempotente via detecção 'done')
        job.status, app_row.result = "tailored", ""
        s.add(job); s.add(app_row); s.commit()
        try:
            result = apply_application(s, job, headless=True)
        except Exception as e:  # noqa: BLE001
            result = {"outcome": "error", "message": str(e)}
        return job_id, job.title, result


def main() -> None:
    dry = "--dry-run" in sys.argv
    threads = max(1, min(_arg_int("--threads", 1), MAX_THREADS))
    init_db()

    # Idempotente na Gupy (re-candidatar retoma a MESMA application id, sem duplicar), então
    # varremos tudo que não está confirmado: applied (re-verifica) + pending_approval + tailored.
    with Session(engine) as s:
        applied = s.exec(
            select(Job).where(Job.status.in_(["applied", "pending_approval", "tailored"]))
        ).all()
        targets: list[int] = []
        print(f"{len(applied)} vaga(s) para reconciliar (applied/pending/tailored).\n")
        for job in applied:
            app_row = s.exec(select(Application).where(Application.job_id == job.id)).first()
            has_cv = bool(app_row and app_row.cv_pdf_path)
            print(f"[{job.id}] {job.title[:44]:44} @ {job.company[:18]:18} cv={has_cv}")
            if has_cv:
                targets.append(job.id)

    if dry:
        print(f"\n[dry-run] reconciliaria {len(targets)} vaga(s) com {threads} thread(s).")
        return

    print(f"\nReconciliando {len(targets)} vaga(s) com {threads} thread(s) (máx. {MAX_THREADS})...\n", flush=True)
    with ThreadPoolExecutor(max_workers=threads) as ex:
        futures = [ex.submit(_reconcile_one, jid) for jid in targets]
        for fut in as_completed(futures):
            jid, title, result = fut.result()
            print(f"  [{jid}] {title[:38]:38} -> {result.get('outcome')}: "
                  f"{result.get('message', '')[:70]}", flush=True)

    print("\n=== ESTADO FINAL ===")
    with Session(engine) as s:
        for job in s.exec(select(Job).where(Job.status.in_(["applied", "tailored", "pending_approval"]))).all():
            a = s.exec(select(Application).where(Application.job_id == job.id)).first()
            print(f"  [{job.id}] status={job.status:16} result={(a.result if a else ''):8} {job.title[:36]}")


if __name__ == "__main__":
    main()

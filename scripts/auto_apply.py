"""Candidatura AUTOMÁTICA AI-driven na Gupy (canal browser) — driver observável.

Dono do BrowserHarness (o plugin nunca abre browser sozinho): abre a vaga logada e chama
`app.platforms.gupy.apply.run_auto_apply`, que segue o fluxo real da Gupy, preenche via IA e
PARA nos pontos irreversíveis salvo ALLOW_REAL_SUBMIT=true + confirmação.

Uso:
    python scripts/auto_apply.py <job_id> [--yes] [--max-steps 14]
Pré-requisitos: sessão logada (scripts/login.py gupy) + CV gerado (scripts/tailor_job.py).
Segurança: sem ALLOW_REAL_SUBMIT=true no .env → DRY-RUN (preenche e para, não envia).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.core import audit  # noqa: E402
from app.core.browser import BrowserHarness  # noqa: E402
from app.core.session import has_session  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import Application, Job, Profile  # noqa: E402
from app.platforms.gupy import apply as gupy_apply  # noqa: E402


def _log(msg: str) -> None:
    print(msg, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Candidatura automática AI-driven (Gupy).")
    ap.add_argument("job_id", type=int)
    ap.add_argument("--real", action="store_true",
                    help="ENVIA de verdade (equivale a ALLOW_REAL_SUBMIT=true) e segue direto, sem perguntar.")
    ap.add_argument("--confirm", action="store_true",
                    help="com --real, pausa pedindo confirmação em cada passo irreversível.")
    ap.add_argument("--max-steps", type=int, default=14)
    args = ap.parse_args()
    allow_real = args.real or settings.allow_real_submit

    init_db()
    with Session(engine) as s:
        job = s.get(Job, args.job_id)
        if job is None:
            raise SystemExit(f"Vaga {args.job_id} não encontrada.")
        app_row = s.exec(select(Application).where(Application.job_id == args.job_id)).first()
        if app_row is None or not app_row.cv_pdf_path:
            raise SystemExit("CV/carta não gerados. Rode: python scripts/tailor_job.py " + str(args.job_id))
        if not has_session(job.platform):
            raise SystemExit(f"Sem sessão '{job.platform}'. Rode: python scripts/login.py {job.platform}")
        profile = s.exec(select(Profile)).first()

        master_cv = profile.to_master_cv()
        extras = profile.to_application_extras()
        cover = ""
        if app_row.cover_letter_path and Path(app_row.cover_letter_path).exists():
            cover = Path(app_row.cover_letter_path).read_text(encoding="utf-8")

        _log(f"Vaga: {job.title} @ {job.company}")
        _log(f"URL: {job.url}")
        _log(f"CV: {app_row.cv_pdf_path}")
        _log(f"EXTRAS (preferências): {extras or '(vazio — perguntas sensíveis vão pausar)'}")
        _log(f"ENVIO REAL={allow_real}  "
             f"({'vai clicar Salvar/Finalizar (com confirmação)' if allow_real else 'DRY-RUN: preenche e para'})\n")

        def confirm(prompt: str) -> bool:
            # --real já é o opt-in explícito de envio → segue direto. --confirm reativa o gate.
            if not args.confirm:
                return True
            try:
                return input(f"\n⚠️  {prompt} [s/N] ").strip().lower() == "s"
            except EOFError:
                return False

        with BrowserHarness(headless=False) as h:
            ctx = h.new_context(job.platform)
            page = ctx.new_page()
            try:
                result = gupy_apply.run_auto_apply(
                    page, job=job, application=app_row, master_cv=master_cv, extras=extras,
                    cover=cover, allow_real=allow_real, confirm=confirm,
                    log_fn=_log, max_steps=args.max_steps,
                )
            except Exception as e:  # noqa: BLE001
                result = {"outcome": "error", "filled": [], "unknown": [], "message": str(e)}
                _log(f"\n! erro no fluxo: {e}")

            outcome = result["outcome"]
            _log(f"\n=== RESULTADO: {outcome} — {result.get('message','')} ===")
            if result.get("unknown"):
                _log(f"Campos para revisão humana: {result['unknown']}")

            if outcome != "sent":
                _log("\n👀 Navegador aberto para inspeção. FECHE a janela do Chromium para encerrar.")
                try:
                    page.wait_for_event("close", timeout=0)
                except Exception:  # noqa: BLE001
                    pass
            try:
                ctx.close()
            except Exception:  # noqa: BLE001
                pass

        # registro
        if outcome == "sent":
            app_row.result, app_row.submitted_at, job.status = "sent", datetime.utcnow(), "applied"
        elif outcome == "needs_review":
            job.status = "pending_approval"
        elif outcome == "dry_run":
            app_row.result = "dry_run"
        s.add(app_row); s.add(job)
        audit.log(s, "auto_apply", platform=job.platform, job_id=job.id,
                  detail={"outcome": outcome, "message": result.get("message", ""),
                          "fields": result.get("filled", [])})
        s.commit()
        _log(f"\nRegistrado: outcome={outcome} | job.status={job.status}")


if __name__ == "__main__":
    main()

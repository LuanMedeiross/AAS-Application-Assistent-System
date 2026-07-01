"""Apply do InHire — mesma trava de segurança da Gupy (aprovação + ALLOW_REAL_SUBMIT).

Envio real é assistido/supervisionado via scripts/apply_job.py (abre a página logada).
"""
from __future__ import annotations

from ...core.schemas import ApplyResult
from ...core.session import has_session


def prepare(job, application) -> ApplyResult:
    if application is None or not application.cv_pdf_path:
        return ApplyResult(ok=False, message="CV/carta não gerados. Rode tailor_job antes.")
    if not has_session("inhire"):
        return ApplyResult(ok=True, submitted=False,
                           message="Pronto para revisão, mas sem sessão InHire — rode scripts/login.py inhire.")
    return ApplyResult(ok=True, submitted=False, message="Pronto para revisão e envio.")


def submit(job, application, *, allow_real: bool = False) -> ApplyResult:
    if not has_session("inhire"):
        return ApplyResult(ok=False, submitted=False,
                           message="Sem sessão InHire. Rode: python scripts/login.py inhire")
    if not allow_real:
        return ApplyResult(ok=True, submitted=False,
                           message="DRY-RUN: envio real desligado (ALLOW_REAL_SUBMIT=false). Nada enviado.")
    return ApplyResult(ok=True, submitted=False,
                       message="Envio real habilitado: rode 'python scripts/apply_job.py {}' "
                               "(supervisionado).".format(job.id))

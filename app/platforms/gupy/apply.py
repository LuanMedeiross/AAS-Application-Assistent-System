"""Apply da Gupy — preparação e envio (com trava de segurança).

Envio de candidatura real é uma ação consequente/irreversível. Aqui:
- `prepare()` valida se há CV/carta gerados e sessão logada — NÃO envia nada.
- `submit()` só envia de verdade com `allow_real=True` E sessão presente; senão roda DRY-RUN.
O envio real é assistido/supervisionado (ver scripts/apply_job.py, que abre a página logada
para o usuário concluir) — nada de auto-submit cego.
"""
from __future__ import annotations

from ...core.schemas import ApplyResult
from ...core.session import has_session


def prepare(job, application) -> ApplyResult:
    """Verifica prontidão para revisão. Não envia nada."""
    if application is None or not application.cv_pdf_path:
        return ApplyResult(ok=False, message="CV/carta não gerados. Rode tailor_job antes.")
    if not has_session("gupy"):
        return ApplyResult(
            ok=True, submitted=False,
            message="Pronto para revisão, mas sem sessão Gupy — rode scripts/login.py gupy antes de enviar.",
        )
    return ApplyResult(ok=True, submitted=False, message="Pronto para revisão e envio.")


def submit(job, application, *, allow_real: bool = False) -> ApplyResult:
    """Envio com trava dupla: exige sessão + allow_real. Sem isso, DRY-RUN (nada enviado)."""
    if not has_session("gupy"):
        return ApplyResult(ok=False, submitted=False,
                           message="Sem sessão Gupy. Rode: python scripts/login.py gupy")
    if not allow_real:
        return ApplyResult(
            ok=True, submitted=False,
            message="DRY-RUN: envio real desligado (ALLOW_REAL_SUBMIT=false). Nada foi enviado à Gupy.",
        )
    # Envio real é SUPERVISIONADO: use scripts/apply_job.py, que abre a página logada para o
    # usuário concluir a candidatura (evita auto-submit cego em formulário multi-etapas da Gupy).
    return ApplyResult(
        ok=True, submitted=False,
        message="Envio real habilitado: rode 'python scripts/apply_job.py {}' para concluir de "
                "forma supervisionada.".format(job.id),
    )

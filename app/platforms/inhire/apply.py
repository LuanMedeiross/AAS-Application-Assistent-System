"""Apply do InHire — ainda NÃO implementado.

O InHire hoje é discovery-only (ver `discovery.py` + `docs/PLATFORMS.md`). Quando a candidatura
for implementada, exponha `run_auto_apply(page, ...)` aqui — o motor real usado pela UI
(`app.services.apply_application`) e por `scripts/auto_apply.py`. O plugin nunca abre o browser
sozinho: recebe `page`/sessão do harness.
"""
from __future__ import annotations

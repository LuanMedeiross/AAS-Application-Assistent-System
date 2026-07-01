"""Login manual por plataforma → salva a sessão (storage_state) para reuso.

Uso: python scripts/login.py <plataforma>
Ex.:  python scripts/login.py gupy

Abre um Chromium visível; você loga normalmente (inclui MFA/captcha manual); ao terminar,
tecle ENTER no terminal para salvar a sessão em data/sessions/<plataforma>.json.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session, select  # noqa: E402

from app.core.browser import BrowserHarness  # noqa: E402
from app.core.session import save_storage_state  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import PlatformSession  # noqa: E402

# URLs de login de CANDIDATO (confirmadas por pesquisa). Gupy/Catho aceitam login social
# (Google/LinkedIn); Indeed pode pedir 2FA — tudo feito manualmente pelo usuário nesta janela.
LOGIN_URLS = {
    "gupy": "https://login.gupy.io/candidates/signin",
    "inhire": "https://inhire.app/login",
    "indeed": "https://secure.indeed.com/account/login",
    "catho": "https://www.catho.com.br/signin/",
    "linkedin": "https://www.linkedin.com/login",
}


def _record(platform: str, path: Path) -> None:
    init_db()
    with Session(engine) as s:
        row = s.exec(select(PlatformSession).where(PlatformSession.platform == platform)).first()
        if row is None:
            row = PlatformSession(platform=platform)
        row.storage_state_path = str(path)
        row.valid = True
        row.last_login_at = datetime.utcnow()
        s.add(row)
        s.commit()


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(f"Uso: python scripts/login.py <{'|'.join(LOGIN_URLS)}>")
    platform = sys.argv[1].lower()
    url = LOGIN_URLS.get(platform, sys.argv[2] if len(sys.argv) > 2 else None)
    if not url:
        raise SystemExit(f"Plataforma desconhecida: {platform}. Informe a URL como 2º argumento.")

    with BrowserHarness(headless=False) as h:
        ctx = h.new_context(platform)
        page = ctx.new_page()
        page.goto(url)
        print(f"\nFaça login em '{platform}' na janela do navegador.")
        input("Quando terminar (logado), tecle ENTER aqui para salvar a sessão... ")
        path = save_storage_state(ctx, platform)
        ctx.close()

    _record(platform, path)
    print(f"Sessão salva: {path}")


if __name__ == "__main__":
    main()

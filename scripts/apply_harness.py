"""Harness de teste isolado. Espelha o agent_harness.py do automation_launcher.

Fase 2: sem plugins ainda → roda um smoke test do navegador (sobe CDP, cria contexto com
stealth, checa navigator.webdriver e o estado da sessão). Fase 3+: roda o discover/apply de um
plugin em dry-run (nunca envia).

Uso: python scripts/apply_harness.py <plataforma> [--keywords "appsec"]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.browser import BrowserHarness  # noqa: E402
from app.core.session import has_session  # noqa: E402
from app.platforms import REGISTRY  # noqa: E402


def _keywords_from_args() -> list[str]:
    if "--keywords" in sys.argv:
        raw = sys.argv[sys.argv.index("--keywords") + 1]
        return [k.strip() for k in raw.split(",") if k.strip()]
    return ["appsec", "pentest", "segurança da informação"]


def discovery_dry_run(platform: str, manifest: dict) -> None:
    if manifest.get("channel") != "api":
        print(f"(dry-run de discovery só implementado p/ canal 'api'; {platform} é "
              f"'{manifest.get('channel')}')")
        return
    from importlib import import_module

    discover = import_module(f"app.platforms.{platform}.discovery").discover
    keywords = _keywords_from_args()
    print(f"[dry-run] {platform} discovery | keywords={keywords}")
    jobs = discover(keywords, limit=5, max_pages=1)
    print(f"[dry-run] {len(jobs)} vaga(s) encontrada(s). Amostra:")
    for j in jobs[:8]:
        print(f"  - {j.title[:55]:55} | {j.company[:22]:22} | {j.location[:18]:18} | {j.url[:40]}")
    print("[dry-run] OK (nada foi enviado).")


def browser_smoke(platform: str) -> None:
    print(f"[smoke] plataforma={platform} | sessão salva: {has_session(platform)}")
    with BrowserHarness(headless=True) as h:
        ctx = h.new_context(platform)
        page = ctx.new_page()
        page.goto("data:text/html,<title>smoke</title><h1>ok</h1>")
        webdriver = page.evaluate("() => navigator.webdriver")
        langs = page.evaluate("() => navigator.languages")
        title = page.title()
        ctx.close()
    print(f"[smoke] navigator.webdriver = {webdriver} (esperado False)")
    print(f"[smoke] navigator.languages = {langs}")
    print(f"[smoke] page.title() = {title!r}")
    assert webdriver is False, "stealth falhou: navigator.webdriver deveria ser False"
    print("[smoke] OK — harness de navegador funcional.")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Uso: python scripts/apply_harness.py <plataforma> [--keywords ...]")
    platform = sys.argv[1].lower()

    plugin = REGISTRY.get(platform)
    if plugin is None:
        print(f"(sem plugin '{platform}' no registry — rodando smoke test do navegador)\n")
        browser_smoke(platform)
        return

    discovery_dry_run(platform, plugin)


if __name__ == "__main__":
    main()

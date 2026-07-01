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

    # Fase 3+: plugin existe → dry-run do discover (não implementado até a Fase 3)
    print(f"Plugin '{platform}' encontrado — dry-run ainda não implementado (Fase 3).")


if __name__ == "__main__":
    main()

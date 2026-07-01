"""Gate de contrato dos plugins (sem rede/DB). Espelha o check_contracts.py do automation_launcher.

Valida que cada plugin em app/platforms/<id>/:
  - NÃO abre navegador sozinho (chromium.launch / sync_playwright) — recebe ctx do harness;
  - NÃO importa a camada web (app.web);
  - tem manifest.py com as chaves obrigatórias (id, name, channel);
  - channel ∈ {api, browser, email}.

Saída: exit 0 se tudo OK; 1 se houver violação. Registry vazio → passa trivialmente.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS = ROOT / "app" / "platforms"

FORBIDDEN = [
    (re.compile(r"\bchromium\.launch\b"), "plugin abrindo Chromium (use o ctx do harness)"),
    (re.compile(r"\bsync_playwright\s*\("), "plugin iniciando Playwright (núcleo gerencia o browser)"),
    (re.compile(r"^\s*(from|import)\s+app\.web\b", re.MULTILINE), "plugin importando app.web (retorno via schemas)"),
]
REQUIRED_MANIFEST_KEYS = ("id", "name", "channel")
VALID_CHANNELS = {"api", "browser", "email"}


def check() -> list[str]:
    problems: list[str] = []
    if not PLATFORMS.exists():
        return problems
    for plugin_dir in sorted(p for p in PLATFORMS.iterdir() if p.is_dir() and not p.name.startswith("__")):
        pyfiles = list(plugin_dir.glob("*.py"))
        # padrões proibidos
        for f in pyfiles:
            text = f.read_text(encoding="utf-8", errors="replace")
            for pattern, msg in FORBIDDEN:
                if pattern.search(text):
                    problems.append(f"{plugin_dir.name}/{f.name}: {msg}")
        # manifest
        manifest = plugin_dir / "manifest.py"
        if not manifest.exists():
            problems.append(f"{plugin_dir.name}: falta manifest.py")
            continue
        mtext = manifest.read_text(encoding="utf-8", errors="replace")
        for key in REQUIRED_MANIFEST_KEYS:
            if not re.search(rf'["\']?{key}["\']?\s*[:=]', mtext):
                problems.append(f"{plugin_dir.name}/manifest.py: chave obrigatória ausente: {key}")
        m = re.search(r'channel\s*[:=]\s*["\'](\w+)["\']', mtext)
        if m and m.group(1) not in VALID_CHANNELS:
            problems.append(f"{plugin_dir.name}/manifest.py: channel inválido '{m.group(1)}'")
    return problems


def main() -> None:
    problems = check()
    if problems:
        print("Contrato de plugins: FALHOU")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("Contrato de plugins: OK")


if __name__ == "__main__":
    main()

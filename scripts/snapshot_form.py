"""Snapshot INTERATIVO do formulário de candidatura (canal browser).

Ferramenta de desenvolvimento (não envia nada). Abre a vaga e, a cada ENTER, captura o DOM da
tela atual: HTML bruto + extração estruturada dos controles de formulário (inputs, selects,
textareas, radios/checkboxes, perguntas de triagem). Serve para mapear o formulário real de uma
plataforma antes de escrever o auto-apply — o form é multi-etapas e dinâmico, então capturamos
etapa por etapa.

Sessão: por padrão abre a página JÁ LOGADA (sessão salva da plataforma). Plataformas cujo apply é
ANÔNIMO (manifest `anonymous_apply=True`, ex.: InHire) dispensam login — o gate de sessão é pulado
e o contexto sobe só com stealth. Use `--anon` para forçar o modo anônimo em qualquer plataforma.

Uso:
    python scripts/snapshot_form.py <job_id>
    python scripts/snapshot_form.py --url https://empresa.gupy.io/jobs/123  [--platform gupy]
    python scripts/snapshot_form.py --url https://clavis.inhire.com.br/vagas/<id> --platform inhire

Fluxo:
    1. Abre a página (logada, ou anônima+stealth para plataformas anônimas).
    2. Você clica "Candidatar-se" / navega pelas etapas NA JANELA.
    3. Pressione ENTER no terminal para capturar a tela atual (repita por etapa).
    4. Digite 'q' + ENTER para sair.

Saídas em: <temp do SO>/application-assistant/<plataforma>_form/  (step_NN.html + step_NN.json +
fields_NN.txt); sobrescreva com a env var SNAPSHOT_OUT_DIR.
Pré-requisito (só canais logados): python scripts/login.py <plataforma>  (sessão salva).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session  # noqa: E402

from app.core.browser import BrowserHarness  # noqa: E402
from app.core.session import has_session  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import Job  # noqa: E402
from app.platforms import REGISTRY  # noqa: E402


def _out_dir(platform: str) -> Path:
    """Saída no temp do SO (artefato de trabalho, fora do projeto; portável entre máquinas).
    Uma pasta por plataforma; sobrescreva com a env var SNAPSHOT_OUT_DIR."""
    return Path(
        os.getenv("SNAPSHOT_OUT_DIR")
        or Path(tempfile.gettempdir()) / "application-assistant" / f"{platform}_form"
    )


def _is_anonymous_apply(platform: str) -> bool:
    """True se o manifest da plataforma declara apply anônimo (dispensa sessão salva)."""
    return bool(REGISTRY.get(platform, {}).get("anonymous_apply"))

# Extrator roda NA PÁGINA: coleta cada controle de formulário com o rótulo associado.
_EXTRACT_JS = r"""
() => {
  const labelFor = (el) => {
    // 1) <label for=id>  2) aria-label  3) aria-labelledby  4) <label> ancestral  5) texto vizinho
    let t = "";
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) t = l.innerText;
    }
    if (!t && el.getAttribute('aria-label')) t = el.getAttribute('aria-label');
    if (!t && el.getAttribute('aria-labelledby')) {
      const ids = el.getAttribute('aria-labelledby').split(/\s+/);
      t = ids.map(i => { const n = document.getElementById(i); return n ? n.innerText : ''; }).join(' ');
    }
    if (!t) { const lab = el.closest('label'); if (lab) t = lab.innerText; }
    if (!t) {
      // pergunta pode estar num container acima (fieldset/legend ou div com role=group)
      const grp = el.closest('fieldset, [role="group"], [role="radiogroup"]');
      if (grp) { const lg = grp.querySelector('legend, [id]'); if (lg) t = lg.innerText; }
    }
    return (t || "").replace(/\s+/g, ' ').trim().slice(0, 300);
  };
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && (r.width + r.height) > 0;
  };
  const controls = [...document.querySelectorAll('input, select, textarea, [role="radio"], [role="checkbox"], [contenteditable="true"]')];
  const fields = controls.map((el, i) => {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || el.getAttribute('role') || tag).toLowerCase();
    const out = {
      idx: i, tag, type,
      name: el.getAttribute('name') || '',
      id: el.id || '',
      placeholder: el.getAttribute('placeholder') || '',
      required: el.required || el.getAttribute('aria-required') === 'true',
      value: (el.value ?? '').toString().slice(0, 120),
      label: labelFor(el),
      visible: visible(el),
      data_testid: el.getAttribute('data-testid') || '',
    };
    if (tag === 'select') {
      out.options = [...el.options].map(o => ({ value: o.value, text: o.text.trim() }));
    }
    if (type === 'radio' || type === 'checkbox') {
      out.checked = !!el.checked || el.getAttribute('aria-checked') === 'true';
    }
    return out;
  });
  // Texto visível de possíveis perguntas de triagem (headings/legends dentro de forms).
  const questions = [...document.querySelectorAll('form legend, form h1, form h2, form h3, form h4, [role="radiogroup"] > *:first-child, [class*="question" i], [class*="Question"]')]
    .map(n => n.innerText.replace(/\s+/g, ' ').trim())
    .filter(t => t.length > 3 && t.length < 300);
  return {
    url: location.href,
    title: document.title,
    fields,
    questions: [...new Set(questions)],
    fileInputs: fields.filter(f => f.type === 'file').length,
  };
}
"""


def _capture(page, attempts: int = 4):
    """Captura (data, html) com tolerância a navegação em andamento. Retorna (None, None) se falhar."""
    for _ in range(attempts):
        # deixa a tela assentar antes de avaliar (a etapa pode estar carregando)
        for state in ("domcontentloaded", "networkidle"):
            try:
                page.wait_for_load_state(state, timeout=8000)
            except Exception:  # noqa: BLE001
                pass
        try:
            data = page.evaluate(_EXTRACT_JS)
            html = page.content()
            return data, html
        except Exception as e:  # noqa: BLE001
            if "context was destroyed" in str(e) or "navigation" in str(e).lower():
                continue  # navegou no meio; tenta de novo depois de reassentar
            print(f"  ! erro inesperado: {e}")
            return None, None
    return None, None


def _resolve_target(args) -> tuple[str, str]:
    """Retorna (url, platform)."""
    if args.url:
        return args.url, args.platform
    init_db()
    with Session(engine) as s:
        job = s.get(Job, int(args.job_id))
        if job is None:
            raise SystemExit(f"Vaga {args.job_id} não encontrada.")
        return job.url, job.platform


def main() -> None:
    ap = argparse.ArgumentParser(description="Snapshot interativo do formulário de candidatura.")
    ap.add_argument("job_id", nargs="?", help="ID da vaga no DB (ou use --url).")
    ap.add_argument("--url", help="URL direta da vaga (dispensa job_id).")
    ap.add_argument("--platform", default="gupy", help="Plataforma da sessão (default: gupy).")
    ap.add_argument("--anon", action="store_true",
                    help="Modo anônimo: pula o gate de sessão (implícito p/ plataformas anônimas).")
    args = ap.parse_args()

    if not args.job_id and not args.url:
        raise SystemExit("Informe <job_id> ou --url.")

    url, platform = _resolve_target(args)
    anon = args.anon or _is_anonymous_apply(platform)
    if not anon and not has_session(platform):
        raise SystemExit(f"Sem sessão '{platform}'. Rode: python scripts/login.py {platform}")

    out_dir = _out_dir(platform)
    out_dir.mkdir(parents=True, exist_ok=True)
    mode = "ANÔNIMO (stealth, sem login)" if anon else "LOGADO (sessão salva)"
    print(f"Vaga: {url}\nPlataforma: {platform}\nModo: {mode}\nSaída: {out_dir}\n")

    with BrowserHarness(headless=False) as h:
        # Anônimo: não passa a plataforma p/ new_context (evita carregar storage_state); só stealth.
        ctx = h.new_context(None if anon else platform)
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded")
        print(f"Página aberta ({mode}). Clique 'Candidatar-se' e navegue pelas etapas na janela.")
        print("A cada tela do formulário, volte aqui e pressione ENTER para capturar. 'q' = sair.\n")

        step = 0
        while True:
            cmd = input(f"[step {step:02d}] ENTER = capturar | q = sair > ").strip().lower()
            if cmd == "q":
                break
            data, html = _capture(page)
            if data is None:
                print("  ! não consegui capturar (página ainda navegando?). "
                      "Espere a tela carregar e tente ENTER de novo.")
                continue

            (out_dir / f"step_{step:02d}.html").write_text(html, encoding="utf-8")
            (out_dir / f"step_{step:02d}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            # Resumo legível dos campos.
            lines = [f"URL: {data['url']}", f"TÍTULO: {data['title']}",
                     f"file inputs: {data['fileInputs']}", "", "PERGUNTAS/HEADINGS:"]
            lines += [f"  - {q}" for q in data["questions"]] or ["  (nenhuma)"]
            lines += ["", "CAMPOS:"]
            for f in data["fields"]:
                vis = "" if f["visible"] else " [oculto]"
                req = " *req" if f["required"] else ""
                opts = ""
                if f.get("options"):
                    opts = " opts=" + " | ".join(o["text"] for o in f["options"][:8])
                lines.append(
                    f"  [{f['idx']:02d}] {f['tag']}/{f['type']}{req}{vis} "
                    f"name={f['name']!r} id={f['id']!r} testid={f['data_testid']!r} "
                    f"label={f['label']!r} ph={f['placeholder']!r}{opts}"
                )
            (out_dir / f"fields_{step:02d}.txt").write_text("\n".join(lines), encoding="utf-8")

            print(f"  ✓ step {step:02d}: {len(data['fields'])} campos, "
                  f"{len(data['questions'])} perguntas, {data['fileInputs']} file input(s). "
                  f"→ step_{step:02d}.[html|json], fields_{step:02d}.txt")
            step += 1

        ctx.close()

    print(f"\nPronto. {step} snapshot(s) em {out_dir}")


if __name__ == "__main__":
    main()

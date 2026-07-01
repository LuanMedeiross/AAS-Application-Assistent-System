"""Render de CV: HTML (Jinja2, template ATS) -> PDF via Chromium (page.pdf).

Usa o Chromium do Playwright (headless) para gerar o PDF — sem WeasyPrint/GTK no Windows.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..core.schemas import TailorResult

_TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    autoescape=select_autoescape(["html"]),
)

# Rótulos de seção por idioma (o conteúdo já vem no idioma da vaga; só os títulos precisam disso).
SECTION_LABELS = {
    "pt": {"summary": "Resumo", "skills": "Competências", "experience": "Experiência",
           "projects": "Projetos", "education": "Formação", "certifications": "Certificações"},
    "en": {"summary": "Summary", "skills": "Skills", "experience": "Experience",
           "projects": "Projects", "education": "Education", "certifications": "Certifications"},
    "es": {"summary": "Resumen", "skills": "Competencias", "experience": "Experiencia",
           "projects": "Proyectos", "education": "Formación", "certifications": "Certificaciones"},
}


def _labels(lang: str | None) -> dict:
    return SECTION_LABELS.get((lang or "pt")[:2].lower(), SECTION_LABELS["en"])


def render_cv_html(contact: dict, result: TailorResult) -> str:
    tmpl = _env.get_template("cv.html")
    return tmpl.render(c=contact, cv=result.cv, lang=result.language, t=_labels(result.language))


def html_to_pdf(html: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html, wait_until="load")
        page.emulate_media(media="print")
        page.pdf(
            path=str(out_path),
            format="A4",
            print_background=True,
            margin={"top": "14mm", "bottom": "14mm", "left": "14mm", "right": "14mm"},
        )
        browser.close()
    return out_path


def render_cv_pdf(contact: dict, result: TailorResult, out_path: Path) -> Path:
    return html_to_pdf(render_cv_html(contact, result), out_path)

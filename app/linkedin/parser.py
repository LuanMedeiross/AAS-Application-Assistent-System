"""Parser do export oficial de dados do LinkedIn (RF-02).

O usuário baixa "Get a copy of your data" no LinkedIn → recebe um ZIP com CSVs
(Profile.csv, Positions.csv, Skills.csv, Education.csv, Certifications.csv, Languages.csv).
Aqui transformamos esses CSVs no dict `master_cv` (mesma forma de curriculum/master_cv.json).

Sem scraping: lê só o arquivo que o próprio usuário exportou. Tolerante a arquivos ausentes.
"""
from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Any


def _read_csv_rows(data: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(data)))


def _g(row: dict[str, str], *keys: str) -> str:
    """Pega o primeiro campo não-vazio entre nomes de coluna possíveis."""
    for k in keys:
        v = row.get(k)
        if v:
            return v.strip()
    return ""


def _ym(date_str: str) -> str | None:
    """Normaliza datas do LinkedIn ('Aug 2025', '2025') para 'YYYY-MM' quando possível."""
    if not date_str:
        return None
    s = date_str.strip()
    months = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
        "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }
    parts = s.replace(",", "").split()
    if len(parts) == 2 and parts[0][:3].lower() in months:
        return f"{parts[1]}-{months[parts[0][:3].lower()]}"
    if s.isdigit():
        return s
    return s


def _load_files(source: str | Path) -> dict[str, str]:
    """Devolve {nome_lower.csv: conteúdo} a partir de um ZIP ou diretório do export."""
    source = Path(source)
    files: dict[str, str] = {}
    # utf-8-sig remove BOM (LinkedIn/Excel costumam exportar CSV com BOM, o que
    # contaminaria o primeiro nome de coluna).
    if source.is_dir():
        for p in source.glob("*.csv"):
            files[p.name.lower()] = p.read_text(encoding="utf-8-sig", errors="replace")
    elif source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".csv"):
                    base = Path(name).name.lower()
                    files[base] = zf.read(name).decode("utf-8-sig", errors="replace")
    else:
        raise ValueError(f"Esperado .zip ou diretório do export do LinkedIn: {source}")
    return files


def parse_linkedin_export(source: str | Path) -> dict[str, Any]:
    """ZIP/diretório do export do LinkedIn -> dict master_cv."""
    files = _load_files(source)

    cv: dict[str, Any] = {
        "full_name": "", "email": "", "phone": "", "location": "",
        "linkedin_url": "", "portfolio_url": "", "seniority": "junior", "summary": "",
        "target_roles": [], "languages": [], "skills": [], "experiences": [],
        "projects": [], "education": [], "certifications": [], "achievements": [],
    }

    # Profile.csv — dados base
    if "profile.csv" in files:
        rows = _read_csv_rows(files["profile.csv"])
        if rows:
            r = rows[0]
            first = _g(r, "First Name")
            last = _g(r, "Last Name")
            cv["full_name"] = " ".join(x for x in (first, last) if x)
            cv["summary"] = _g(r, "Summary")
            cv["location"] = _g(r, "Geo Location", "Location")
            headline = _g(r, "Headline")
            if headline:
                cv["target_roles"] = [headline]

    # Email Addresses.csv
    if "email addresses.csv" in files:
        rows = _read_csv_rows(files["email addresses.csv"])
        if rows:
            cv["email"] = _g(rows[0], "Email Address")

    # Positions.csv — experiências
    if "positions.csv" in files:
        for r in _read_csv_rows(files["positions.csv"]):
            desc = _g(r, "Description")
            cv["experiences"].append({
                "company": _g(r, "Company Name"),
                "title": _g(r, "Title"),
                "start": _ym(_g(r, "Started On")),
                "end": _ym(_g(r, "Finished On")) or None,
                "location": _g(r, "Location"),
                "bullets": [b.strip() for b in desc.split("\n") if b.strip()] or ([desc] if desc else []),
            })

    # Education.csv
    if "education.csv" in files:
        for r in _read_csv_rows(files["education.csv"]):
            cv["education"].append({
                "school": _g(r, "School Name"),
                "degree": _g(r, "Degree Name", "Notes"),
                "start": _ym(_g(r, "Start Date")),
                "end": _ym(_g(r, "End Date")),
                "status": "",
            })

    # Skills.csv
    if "skills.csv" in files:
        cv["skills"] = [_g(r, "Name") for r in _read_csv_rows(files["skills.csv"]) if _g(r, "Name")]

    # Certifications.csv
    if "certifications.csv" in files:
        cv["certifications"] = [
            _g(r, "Name") for r in _read_csv_rows(files["certifications.csv"]) if _g(r, "Name")
        ]

    # Languages.csv
    if "languages.csv" in files:
        for r in _read_csv_rows(files["languages.csv"]):
            name = _g(r, "Name")
            prof = _g(r, "Proficiency")
            if name:
                cv["languages"].append(f"{name} — {prof}" if prof else name)

    return cv

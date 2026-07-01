"""Gestão de sessão por plataforma (storage_state do Playwright).

Login é manual (o usuário loga uma vez via scripts/login.py); aqui só salvamos/carregamos o
storage_state em data/sessions/<plataforma>.json. NUNCA guardamos usuário/senha.
"""
from __future__ import annotations

from pathlib import Path

from ..config import settings


def session_path(platform: str) -> Path:
    return settings.sessions_dir / f"{platform}.json"


def has_session(platform: str) -> bool:
    p = session_path(platform)
    return p.exists() and p.stat().st_size > 0


def save_storage_state(context, platform: str) -> Path:
    """Salva o storage_state atual do contexto (cookies + localStorage) da plataforma."""
    settings.sessions_dir.mkdir(parents=True, exist_ok=True)
    path = session_path(platform)
    context.storage_state(path=str(path))
    return path

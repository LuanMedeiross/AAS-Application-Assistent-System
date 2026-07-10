"""Manifest declarativo do plugin Gupy (canal api). Ver docs/PLATFORMS.md."""
from __future__ import annotations

from .discovery import discover

MANIFEST = {
    "id": "gupy",
    "name": "Gupy",
    "channel": "api",
    "endpoints": {
        # discovery público, sem auth (backend do portal.gupy.io)
        "jobs": "https://employability-portal.gupy.io/api/v1/jobs",
    },
    "captcha": None,  # canal api não enfrenta captcha
    # Currículo montado na própria Gupy: geramos o conteúdo (alimenta as respostas do
    # form_agent), mas NÃO renderizamos PDF. Ver SPEC.md §4/§5.
    "application": {"cv": "onplatform", "cover_letter": True},
}


def build() -> dict:
    """Monta o plugin (lazy). Retorna o spec consumido pelo harness/registry."""
    return {"manifest": MANIFEST, "discover": discover}

"""Manifest do plugin InHire (canal api, por empresa/tenant). Ver docs/plataformas.md."""
from __future__ import annotations

from .apply import prepare, submit
from .discovery import discover

MANIFEST = {
    "id": "inhire",
    "name": "InHire",
    "channel": "api",
    "endpoints": {"jobs_lean": "https://api.inhire.app/job-posts/public/pages/lean"},
    "captcha": None,
}


def build() -> dict:
    return {"manifest": MANIFEST, "discover": discover, "prepare": prepare, "submit": submit}

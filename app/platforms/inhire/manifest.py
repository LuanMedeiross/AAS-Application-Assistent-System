"""Manifest do plugin InHire (canal api, por empresa/tenant). Ver docs/PLATFORMS.md."""
from __future__ import annotations

from .discovery import discover

MANIFEST = {
    "id": "inhire",
    "name": "InHire",
    "channel": "api",
    "endpoints": {"jobs_lean": "https://api.inhire.app/job-posts/public/pages/lean"},
    "captcha": None,
    # The public apply flow needs no candidate login (the SPA only sends Authorization when an
    # accessToken exists). So the harness must NOT require a saved session for inhire — see
    # INHIRE.md §4 and services.apply_application. Discovery is anonymous too.
    "anonymous_apply": True,
    # Requer um arquivo de currículo real (upload): renderizamos o PDF. Ver SPEC.md §4/§5.
    "application": {"cv": "file", "cover_letter": True},
}


def build() -> dict:
    return {"manifest": MANIFEST, "discover": discover}

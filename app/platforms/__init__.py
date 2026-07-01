"""Registry de plugins de plataforma.

Cada plugin se registra aqui via import estático (como no automation_launcher). Para adicionar
uma plataforma: crie app/platforms/<id>/ (manifest/discovery/apply) e some o MANIFEST aqui.
"""
from __future__ import annotations

from .gupy.manifest import MANIFEST as _gupy

REGISTRY: dict = {m["id"]: m for m in (_gupy,)}

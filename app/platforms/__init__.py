"""Registry de plugins de plataforma.

Cada plugin se registra aqui via import estático (como no automation_launcher). Vazio na
Fase 1 — o primeiro plugin (Gupy) entra na Fase 3.
"""

REGISTRY: dict = {}

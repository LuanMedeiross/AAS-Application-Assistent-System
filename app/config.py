"""Configuração central — lê o .env e expõe caminhos/segredos.

Segredos nunca têm default real; ficam vazios se não configurados (ver .env.example).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    # Segredos / IA
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = "https://api.deepseek.com"
    # Modelo mais forte da DeepSeek (R1, raciocínio) para tudo — ranking e geração.
    # reasoner não suporta response_format=json_object; o ai/deepseek._extract_json cobre isso.
    model_rank: str = "deepseek-reasoner"
    model_generate: str = "deepseek-reasoner"

    captcha_api_key: str = os.getenv("CAPTCHA_API_KEY", "")

    # Trava de segurança: enquanto False, "Aprovar e enviar" roda em DRY-RUN (não envia
    # candidatura real). Só True (via .env ALLOW_REAL_SUBMIT=true) permite envio real.
    allow_real_submit: bool = os.getenv("ALLOW_REAL_SUBMIT", "false").lower() == "true"

    # InHire é por empresa (tenant): lista de empresas-alvo (slugs), separadas por vírgula.
    inhire_tenants: list = [
        t.strip() for t in os.getenv("INHIRE_TENANTS", "").split(",") if t.strip()
    ]

    # SMTP (Fase 7)
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587") or 587)
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")

    # Caminhos
    base_dir: Path = BASE_DIR
    data_dir: Path = BASE_DIR / "data"
    sessions_dir: Path = BASE_DIR / "data" / "sessions"
    generated_dir: Path = BASE_DIR / "data" / "generated"
    curriculum_dir: Path = BASE_DIR / "curriculum"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.sessions_dir, self.generated_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()

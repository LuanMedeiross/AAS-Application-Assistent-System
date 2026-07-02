"""Configuração central — lê o .env e expõe caminhos/segredos.

Segredos nunca têm default real; ficam vazios se não configurados (ver .env.example).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env(*names: str, default: str = "") -> str:
    """First non-empty env var among `names`, else `default`."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


class Settings:
    # LLM provider (any OpenAI-compatible endpoint: DeepSeek, or a local server such as Ollama /
    # LM Studio / vLLM).
    llm_api_key: str = _env("LLM_API_KEY")
    llm_base_url: str = _env("LLM_BASE_URL", default="https://api.deepseek.com")
    # Ranking = bounded judgment task -> a fast/cheap chat model (quality comes from the rubric in
    # ai/ranker.py). Generation (CV/cover) = quality-critical -> a reasoner-class model.
    model_rank: str = _env("MODEL_RANK", default="deepseek-chat")
    model_generate: str = _env("MODEL_GENERATE", default="deepseek-reasoner")
    # JSON output mode: "auto" sends response_format=json_object unless the model name looks like a
    # reasoner; "on" always sends it; "off" never (for local servers that reject it — _extract_json
    # still parses the reply). Set LLM_JSON_MODE=off for local models that don't support it.
    llm_json_mode: str = _env("LLM_JSON_MODE", default="auto").lower()
    # Per-attempt timeout (s) and retries. The openai SDK backs off on transient errors
    # (connection/408/409/429/5xx). Generous because a reasoner (CV) is slow.
    llm_timeout: float = float(_env("LLM_TIMEOUT", default="180"))
    llm_max_retries: int = int(_env("LLM_MAX_RETRIES", default="3"))

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

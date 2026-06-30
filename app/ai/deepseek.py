"""Cliente DeepSeek (SDK openai apontando para api.deepseek.com).

Expõe `chat_json()` — força saída JSON e (opcional) valida contra um modelo Pydantic.
A chave só é exigida quando há chamada real; importar este módulo não falha sem .env.
"""
from __future__ import annotations

import json
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

from ..config import settings
from ..core.schemas import SeniorityResult

T = TypeVar("T", bound=BaseModel)

_client = None


def _get_client():
    global _client
    if _client is None:
        if not settings.deepseek_api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY não configurada — preencha o .env (ver .env.example)."
            )
        from openai import OpenAI

        _client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
    return _client


def chat_json(
    system: str,
    user: str,
    *,
    model: Optional[str] = None,
    schema: Optional[Type[T]] = None,
    temperature: float = 0.3,
) -> dict | T:
    """Chama o DeepSeek pedindo JSON. Se `schema` for dado, valida e retorna a instância."""
    client = _get_client()
    resp = client.chat.completions.create(
        model=model or settings.model_generate,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    content = resp.choices[0].message.content or "{}"
    data = json.loads(content)
    if schema is not None:
        return schema.model_validate(data)
    return data


def derive_seniority(master_cv: dict) -> SeniorityResult:
    """IA sugere a senioridade a partir do master_cv (usuário confirma no dashboard)."""
    system = (
        "Você classifica a senioridade de um profissional de cibersegurança em uma de: "
        "entry, junior, mid, senior. Considere tempo e relevância de experiência, "
        "certificações e formação. Responda em JSON: {\"seniority\": \"...\", \"reason\": \"...\"}."
    )
    user = json.dumps(master_cv, ensure_ascii=False)
    return chat_json(system, user, model=settings.model_rank, schema=SeniorityResult)

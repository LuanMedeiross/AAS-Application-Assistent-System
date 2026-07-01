"""Cliente DeepSeek (SDK openai apontando para api.deepseek.com).

Expõe `chat_json()` — força saída JSON e (opcional) valida contra um modelo Pydantic.
A chave só é exigida quando há chamada real; importar este módulo não falha sem .env.
"""
from __future__ import annotations

import json
import re
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

from ..config import settings
from ..core.schemas import SeniorityResult

T = TypeVar("T", bound=BaseModel)

_client = None


def _extract_json(content: str) -> dict:
    """Extrai um objeto JSON da resposta do modelo, tolerante a fences/markdown.

    deepseek-reasoner não suporta response_format=json_object, então a saída pode vir com
    ```json ... ``` ou texto ao redor. Tentamos json.loads direto; senão, o primeiro {...}.
    """
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end > start:
        return json.loads(content[start : end + 1])
    raise ValueError(f"Resposta sem JSON reconhecível: {content[:200]!r}")


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
    model = model or settings.model_generate
    kwargs: dict = {"temperature": temperature}
    # reasoner não suporta response_format=json_object; chat suporta.
    if "reasoner" not in model:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        **kwargs,
    )
    content = resp.choices[0].message.content or "{}"
    data = _extract_json(content)
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

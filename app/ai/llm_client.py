"""LLM client (openai SDK against any OpenAI-compatible endpoint; provider configured via
LLM_BASE_URL / MODEL_RANK / MODEL_GENERATE — DeepSeek by default, or a local server such as
Ollama / LM Studio / vLLM).

Exposes `chat_json()` — forces JSON output and optionally validates it against a Pydantic model.
The API key is only required on a real call; importing this module never fails without a .env.
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

    Reasoner models (and JSON mode = off) don't emit a strict json_object, so the reply may come
    wrapped in ```json ... ``` or with surrounding text. Try json.loads first, else the first {...}.
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
        if not settings.llm_api_key:
            raise RuntimeError(
                "LLM_API_KEY not set — fill it in .env (see .env.example). "
                "For a local server, any non-empty dummy value works."
            )
        from openai import OpenAI

        _client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout,
            max_retries=settings.llm_max_retries,
        )
    return _client


def _use_json_mode(model: str) -> bool:
    """Whether to send response_format=json_object, per LLM_JSON_MODE (auto | on | off)."""
    mode = settings.llm_json_mode
    if mode == "on":
        return True
    if mode == "off":
        return False
    return "reasoner" not in model   # auto: reasoner models reject it


def chat_json(
    system: str,
    user: str,
    *,
    model: Optional[str] = None,
    schema: Optional[Type[T]] = None,
    temperature: float = 0.3,
) -> dict | T:
    """Call the LLM asking for JSON. If `schema` is given, validate and return the instance."""
    client = _get_client()
    model = model or settings.model_generate
    kwargs: dict = {"temperature": temperature}
    # response_format=json_object is rejected by reasoner models and by some local servers.
    if _use_json_mode(model):
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

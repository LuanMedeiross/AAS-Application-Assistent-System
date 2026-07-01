"""Pipeline de captcha (2Captcha), acionado quando o canal `browser` for bloqueado.

Portado de automation_launcher/backend/captcha.py. Import da lib é lazy: importar este
módulo não exige `2captcha-python` instalado nem chave — só quando há solve real.
"""
from __future__ import annotations

import logging

from ..config import settings

log = logging.getLogger(__name__)


class CaptchaBalanceError(Exception):
    """Saldo da conta 2Captcha esgotado (ERROR_ZERO_BALANCE)."""


def _get_solver(default_timeout: int = 120):
    if not settings.captcha_api_key:
        raise RuntimeError("CAPTCHA_API_KEY não configurada (.env).")
    from twocaptcha import TwoCaptcha

    return TwoCaptcha(apiKey=settings.captcha_api_key, pollingInterval=5, defaultTimeout=default_timeout)


def get_balance() -> float | None:
    try:
        return float(_get_solver().balance())
    except Exception as e:  # noqa: BLE001
        log.warning("Não foi possível consultar saldo 2Captcha: %s", e)
        return None


def solve(
    captcha_type: str,
    *,
    sitekey: str | None = None,
    url: str | None = None,
    body: str | None = None,
    options: dict | None = None,
    captcha_script: str | None = None,
) -> str | None:
    """Resolve um captcha e retorna o token, ou None. Tipos: cloudflare-turnstile, hcaptcha,
    recaptcha-v2, normal (imagem)."""
    from twocaptcha import ApiException

    solver = _get_solver(default_timeout=200 if captcha_type == "hcaptcha" else 120)
    token = None
    try:
        if captcha_type == "cloudflare-turnstile":
            token = solver.turnstile(sitekey=sitekey, url=url, action="challenge")
        elif captcha_type == "hcaptcha":
            token = solver.hcaptcha(sitekey=sitekey, url=url)
        elif captcha_type == "recaptcha-v2":
            invisible = 1 if not options or options.get("invisible", 1) else 0
            token = solver.recaptcha(sitekey=sitekey, url=url, invisible=invisible)
        elif captcha_type == "normal":
            token = solver.normal(body, **(options or {}))
        else:
            log.warning("Tipo de captcha desconhecido: %s", captcha_type)
        if token:
            token = token.get("code")
            log.info("2Captcha resolveu o captcha (%s)", captcha_type)
    except TimeoutError:
        log.warning("Captcha não resolvido no tempo esperado")
    except ApiException as e:
        if "ERROR_ZERO_BALANCE" in str(e):
            raise CaptchaBalanceError() from e
        log.exception("Erro ao resolver captcha")
    except Exception:  # noqa: BLE001
        log.exception("Erro ao resolver captcha")
    return token

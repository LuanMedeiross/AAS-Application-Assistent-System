"""Cliente HTTP para o canal `api` — curl_cffi com TLS impersonation (Chrome), fallback requests.

Portado de automation_launcher/backend/http_client.py. APIs como a da Gupy podem checar o
fingerprint TLS; o impersonate reduz bloqueio sem navegador.
"""
from __future__ import annotations

import importlib
import logging

import requests

log = logging.getLogger(__name__)

IMPERSONATE = "chrome"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

try:
    from curl_cffi import requests as _cffi
    HAS_CFFI = True
except Exception:  # noqa: BLE001
    _cffi = None
    HAS_CFFI = False
    log.info("curl_cffi indisponível — usando requests padrão (sem impersonate de TLS)")


def new_session(proxies: dict | None = None):
    session = None
    if HAS_CFFI:
        try:
            session = _cffi.Session(impersonate=IMPERSONATE)
        except Exception:  # noqa: BLE001
            log.warning("Falha ao criar sessão curl_cffi; caindo para requests", exc_info=True)
            session = None
    if session is None:
        session = requests.Session()
        session.headers.setdefault("User-Agent", DEFAULT_UA)
    if proxies:
        session.proxies = proxies
    return session


_errors = [requests.exceptions.RequestException]
if HAS_CFFI:
    for _mod_name, _attr in (
        ("curl_cffi.requests.exceptions", "RequestException"),
        ("curl_cffi.requests.errors", "RequestsError"),
        ("curl_cffi", "CurlError"),
        ("curl_cffi", "RequestsError"),
    ):
        try:
            _exc = getattr(importlib.import_module(_mod_name), _attr, None)
            if isinstance(_exc, type) and issubclass(_exc, BaseException):
                _errors.append(_exc)
        except Exception:  # noqa: BLE001
            pass

HTTP_ERRORS = tuple(dict.fromkeys(_errors))

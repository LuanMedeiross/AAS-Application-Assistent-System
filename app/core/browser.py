"""Chromium único via CDP + harness de contexto (canal `browser`).

Portado de automation_launcher/backend/browser.py. Sobe UM Chromium com
--remote-debugging-port e cada contexto se conecta via connect_over_cdp(). O binário do
Chromium é o que o Playwright instala (`playwright install chromium`).

BrowserHarness encapsula o ciclo: inicia o Playwright, sobe o servidor, conecta e entrega
contextos já com stealth + storage_state da sessão manual.
"""
from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import tempfile
import time

from .session import session_path, has_session
from .stealth import get_stealth_script

log = logging.getLogger(__name__)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ChromiumServer:
    """Sobe e derruba um único Chromium acessível por CDP."""

    def __init__(self, executable_path: str, headless: bool = False, extra_args: list[str] | None = None):
        self.executable_path = executable_path
        self.headless = headless
        self.extra_args = extra_args or []
        self.port: int | None = None
        self.cdp_url: str | None = None
        self._proc: subprocess.Popen | None = None
        self._user_data_dir: str | None = None

    def start(self, timeout: float = 30.0) -> str:
        self.port = _free_port()
        self._user_data_dir = tempfile.mkdtemp(prefix="aa_chromium_")
        args = [
            self.executable_path,
            f"--remote-debugging-port={self.port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={self._user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-startup-window",
            #"--window-position=-32000,-32000",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
        ]
        if self.headless:
            args.append("--headless=new")
        args.extend(self.extra_args)

        log.info("Subindo Chromium (CDP) na porta %s | headless=%s", self.port, self.headless)
        self._proc = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ}
        )
        self._wait_until_ready(timeout)
        self.cdp_url = f"http://127.0.0.1:{self.port}"
        return self.cdp_url

    def _wait_until_ready(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"Chromium encerrou antes de abrir a porta CDP (código {self._proc.returncode}). "
                    "Rodou 'playwright install chromium'?"
                )
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.3):
                    return
            except OSError:
                time.sleep(0.2)
        self.stop()
        raise RuntimeError(f"Timeout esperando o Chromium abrir a porta CDP {self.port}.")

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        if self._user_data_dir:
            shutil.rmtree(self._user_data_dir, ignore_errors=True)
            self._user_data_dir = None
        self.cdp_url = None
        self.port = None


class BrowserHarness:
    """Context manager: Playwright + Chromium CDP + contextos com stealth/sessão.

    Uso:
        with BrowserHarness(headless=False) as h:
            ctx = h.new_context("gupy")   # carrega data/sessions/gupy.json se existir
            page = ctx.new_page(); page.goto(...)
    """

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._pw = None
        self._server: ChromiumServer | None = None
        self._browser = None

    def __enter__(self) -> "BrowserHarness":
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        executable = self._pw.chromium.executable_path
        self._server = ChromiumServer(executable, headless=self.headless)
        cdp_url = self._server.start()
        self._browser = self._pw.chromium.connect_over_cdp(cdp_url)
        return self

    def new_context(self, platform: str | None = None):
        """Cria um BrowserContext com stealth e, se houver, a sessão salva da plataforma."""
        kwargs: dict = {"ignore_https_errors": True}
        if platform and has_session(platform):
            kwargs["storage_state"] = str(session_path(platform))
        ctx = self._browser.new_context(**kwargs)
        ctx.add_init_script(get_stealth_script())
        return ctx

    def __exit__(self, *exc) -> None:
        try:
            if self._browser:
                self._browser.close()
        except Exception:  # noqa: BLE001
            pass
        if self._server:
            self._server.stop()
        if self._pw:
            self._pw.stop()

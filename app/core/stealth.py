"""Script de stealth injetado via add_init_script ANTES do goto.

Portado de automation_launcher/backend/utils.py. Reduz detecção (navigator.webdriver,
languages, plugins, WebGL, timezone). Não promete invisibilidade — reduz tells comuns.
"""
from __future__ import annotations

_STEALTH_SCRIPT = """
(() => {
  try {
    Object.defineProperty(navigator, 'webdriver', { get: () => false, configurable: true });
    Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US'], configurable: true });
    Object.defineProperty(navigator, 'language', { get: () => 'pt-BR', configurable: true });
    try { window.chrome = window.chrome || { runtime: {} }; } catch (e) {}
    try {
      const fakePlugin = { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' };
      Object.defineProperty(navigator, 'plugins', { get: () => [fakePlugin], configurable: true });
      Object.defineProperty(navigator, 'mimeTypes', { get: () => [{ type: 'application/pdf', suffixes: 'pdf', description: '' }], configurable: true });
    } catch (e) {}
    try {
      const origQuery = navigator.permissions && navigator.permissions.query;
      if (origQuery) {
        navigator.permissions.query = (params) => {
          if (params && params.name === 'notifications') {
            return Promise.resolve({ state: Notification.permission });
          }
          return origQuery.call(navigator.permissions, params);
        };
      }
    } catch (e) {}
    try {
      const getParameter = WebGLRenderingContext.prototype.getParameter;
      WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 0x9245) return 'Intel Inc.';
        if (parameter === 0x9246) return 'Intel Iris OpenGL Engine';
        return getParameter.call(this, parameter);
      };
    } catch (e) {}
    try {
      const origResolved = Intl.DateTimeFormat.prototype.resolvedOptions;
      Intl.DateTimeFormat.prototype.resolvedOptions = function() {
        const r = origResolved.call(this);
        r.timeZone = 'America/Sao_Paulo';
        return r;
      };
    } catch (e) {}
  } catch (err) {
    try { console.warn('stealth init script error', err); } catch(e) {}
  }
})();
"""


def get_stealth_script() -> str:
    return _STEALTH_SCRIPT

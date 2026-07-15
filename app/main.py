"""Entrada do app — cria o FastAPI, inicializa o DB e monta as rotas do dashboard.

Rodar: uvicorn app.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI

from .db import init_db
from .web.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="Application Assistant System")

    @app.on_event("startup")
    def _startup() -> None:
        init_db()

    app.include_router(router)
    return app


app = create_app()

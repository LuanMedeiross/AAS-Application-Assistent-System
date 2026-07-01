"""Engine SQLite + helpers de sessão (SQLModel)."""
from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

settings.ensure_dirs()

engine = create_engine(
    settings.db_url,
    echo=False,
    # check_same_thread=False + timeout: a fila de candidatura em lote roda em até 5 threads;
    # o timeout faz um writer esperar o lock do SQLite em vez de estourar "database is locked".
    connect_args={"check_same_thread": False, "timeout": 30},
)


def init_db() -> None:
    """Cria as tabelas (idempotente). Importa models p/ registrar no metadata."""
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session

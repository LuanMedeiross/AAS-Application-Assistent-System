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
    _run_light_migrations()


def _run_light_migrations() -> None:
    """Add columns that were introduced after a table was first created.

    SQLModel's create_all only creates missing tables, never adds missing columns to existing
    ones. For this single-user SQLite app we handle the few additive migrations by hand, guarded
    by PRAGMA table_info so each ALTER runs at most once.
    """
    additions = {
        # table -> {column: DDL type with default}
        "application": {"form_qa": "JSON DEFAULT '[]'"},
        "job": {"hidden": "BOOLEAN DEFAULT 0"},
    }
    with engine.begin() as conn:
        for table, columns in additions.items():
            existing = {row[1] for row in conn.exec_driver_sql(
                f"PRAGMA table_info({table})").fetchall()}
            for column, ddl in columns.items():
                if column not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session

"""Database connection lifetime and transaction boundaries."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from backend.core.config import Settings

Row = dict[str, Any]
DatabaseConnection = psycopg.Connection[Row]


def connection_parameters(settings: Settings) -> dict[str, int | str]:
    existing_options = conninfo_to_dict(settings.database_url).get('options', '')
    options = (
        f'{existing_options} -c statement_timeout={settings.db_statement_timeout_ms} '
        f'-c lock_timeout={settings.db_lock_timeout_ms}'
    )
    return {'connect_timeout': settings.db_connect_timeout_seconds, 'options': options}


@contextmanager
def connection(settings: Settings) -> Iterator[DatabaseConnection]:
    """Commit on success and roll back on exceptions using psycopg's context."""
    with psycopg.connect(
        settings.database_url,
        row_factory=dict_row,
        **connection_parameters(settings),
    ) as conn:
        yield conn


@contextmanager
def read_snapshot(settings: Settings) -> Iterator[DatabaseConnection]:
    """Keep a collection's rows and count on the same PostgreSQL snapshot."""
    with connection(settings) as conn:
        conn.read_only = True
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        yield conn

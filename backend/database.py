"""Database connection lifetime and transaction boundaries."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import replace
import asyncio
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

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


def reset_transaction_defaults(conn: DatabaseConnection) -> None:
    conn.read_only = None
    conn.isolation_level = None


@asynccontextmanager
async def pooled_settings(settings: Settings) -> AsyncIterator[Settings]:
    if not settings.db_pool_max_size:
        yield settings
        return

    pool = ConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=settings.db_pool_max_size,
        max_waiting=80,
        timeout=settings.db_connect_timeout_seconds,
        kwargs={'row_factory': dict_row, **connection_parameters(settings)},
        reset=reset_transaction_defaults,
        check=ConnectionPool.check_connection,
        name='queuesense',
        open=False,
    )
    pool.open()
    try:
        yield replace(settings, connection_pool=pool)
    finally:
        await asyncio.to_thread(pool.close)


@contextmanager
def connection(settings: Settings) -> Iterator[DatabaseConnection]:
    """Commit on success and roll back on exceptions using psycopg's context."""
    if settings.connection_pool is not None:
        with settings.connection_pool.connection() as conn:
            yield conn
        return

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

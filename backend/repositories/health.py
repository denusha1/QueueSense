"""Minimal database readiness query used by the legacy health route."""

from backend.database import connection


def check_database(settings) -> None:
    with connection(settings) as conn:
        conn.execute('SELECT 1 FROM auth_sessions LIMIT 1')

"""Atomic request accounting on the shared PostgreSQL primary."""

from backend.core.errors import ServiceError
from backend.database import DatabaseConnection

CONSUME = """
WITH tick AS (
    SELECT extract(epoch FROM statement_timestamp()) AS now
), budget AS (
    INSERT INTO api_traffic_budgets AS current (policy, subject, window_start, requests)
    SELECT %s, %s, floor(now / 60)::bigint * 60, 1 FROM tick
    ON CONFLICT (policy, subject) DO UPDATE
    SET window_start = EXCLUDED.window_start,
        requests = CASE WHEN current.window_start < EXCLUDED.window_start
                        THEN 1 ELSE current.requests + 1 END
    WHERE current.window_start < EXCLUDED.window_start
       OR (current.window_start = EXCLUDED.window_start AND current.requests < %s)
    RETURNING requests
)
SELECT EXISTS (SELECT 1 FROM budget) AS allowed,
       ceil((floor(now / 60) + 1) * 60 - now)::int AS retry_after
FROM tick
"""


def consume(conn: DatabaseConnection, policy: str, subject, limit: int) -> None:
    result = conn.execute(CONSUME, (policy, subject, limit)).fetchone()
    if not result['allowed']:
        raise ServiceError(
            429,
            'Too many requests. Wait before retrying.',
            headers={'Retry-After': str(max(1, result['retry_after']))},
        )


def prune(conn: DatabaseConnection) -> None:
    conn.execute("""
        DELETE FROM api_traffic_budgets
        WHERE (policy, subject) IN (
            SELECT policy, subject FROM api_traffic_budgets
            WHERE window_start < extract(epoch FROM statement_timestamp()) - 86400
            ORDER BY window_start LIMIT 1000 FOR UPDATE SKIP LOCKED
        )
        AND window_start < extract(epoch FROM statement_timestamp()) - 86400
    """)

"""Write audit records inside the caller's business transaction."""

from psycopg.types.json import Jsonb


def audit(conn, user, action, entity, entity_id, details=None, actor_type=None):
    conn.execute(
        'INSERT INTO audit_logs(user_id,action,entity_type,entity_id,actor_type,details) '
        'VALUES(%s,%s,%s,%s,%s,%s)',
        (
            user['id'] if user else None,
            action,
            entity,
            entity_id,
            actor_type or ('staff' if user else 'system'),
            Jsonb(details or {}),
        ),
    )

"""Read the current staff grant for database-managed permissions."""

from backend.core.errors import ServiceError
from backend.database import DatabaseConnection


def require_permission(
    conn: DatabaseConnection, actor_id: str, permission: str
) -> None:
    row = conn.execute(
        'SELECT 1 FROM users u JOIN role_permissions rp ON rp.role_code=u.role '
        'WHERE u.id=%s AND u.is_active AND rp.permission_code=%s',
        (actor_id, permission),
    ).fetchone()
    if not row:
        raise ServiceError(
            403, 'Your account does not have permission for this action.'
        )

"""Staff traffic policies keyed by the authenticated account ID."""

from backend.core.config import Settings
from backend.database import connection
from backend.repositories import traffic

READ_METHODS = {'GET', 'HEAD'}
STAFF_LIMITS = {
    'admin': (180, 60),
    'reception': (240, 120),
    'doctor': (180, 60),
    'manager': (120, 30),
}
ADMIN_PATHS = {'/audit', '/audit/page', '/data/import', '/reports/export'}


def enforce_staff(settings: Settings, method: str, path: str, user) -> None:
    read_limit, write_limit = STAFF_LIMITS[user['role']]
    read = method in READ_METHODS
    if path.startswith('/admin/') or path in ADMIN_PATHS:
        policy, limit = ('admin-read', 60) if read else ('admin-write', 30)
    else:
        policy, limit = (
            ('staff-read', read_limit) if read else ('staff-write', write_limit)
        )
    with connection(settings) as conn:
        traffic.consume(conn, policy, user['id'], limit)

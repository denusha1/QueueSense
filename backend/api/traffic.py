"""Select budgets after authenticating a staff account or resolving a private link."""

from fastapi import Depends, Request

from backend.api.dependencies import AppSettings
from backend.core.security import valid_private_key
from backend.database import connection
from backend.repositories import traffic
from backend.services.traffic import READ_METHODS

QUEUE_LINK = 'SELECT id, false AS kiosk FROM queue_tokens WHERE public_key=%s'
ARRIVAL_LINK = """
    SELECT id, false AS kiosk FROM appointments WHERE public_key=%s
    UNION ALL
    SELECT id, true AS kiosk FROM checkin_kiosks
    WHERE public_key=%s AND revoked_at IS NULL AND expires_at > now()
    LIMIT 1
"""


def limit_public_link(request: Request, settings: AppSettings) -> None:
    key = request.path_params['key']
    if not valid_private_key(key):
        return
    queue_link = request.url.path.startswith('/patient/')
    with connection(settings) as conn:
        row = conn.execute(
            QUEUE_LINK if queue_link else ARRIVAL_LINK,
            (key,) if queue_link else (key, key),
        ).fetchone()
        if row:
            read = request.method in READ_METHODS
            if row['kiosk']:
                policy, limit = ('kiosk-read', 120) if read else ('kiosk-write', 60)
            else:
                policy, limit = ('link-read', 40) if read else ('link-write', 12)
            traffic.consume(conn, policy, row['id'], limit)


PUBLIC_LINK_TRAFFIC = [Depends(limit_public_link)]

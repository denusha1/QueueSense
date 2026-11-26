"""Capacity-limited appointments, idempotent QR arrivals and committed queue events."""

import secrets
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timedelta

import psycopg
from psycopg import sql
from psycopg.errors import UniqueViolation
from pydantic import Field

from backend.core.authorization import authorize
from backend.core.config import CLINIC_TIMEZONE as TZ
from backend.core.config import Settings
from backend.core.errors import ServiceError
from backend.core.security import valid_private_key
from backend.database import connection, connection_parameters
from backend.repositories.audit import audit
from backend.repositories.queue import lock_queue_writes
from backend.schemas.product import Input
from backend.services.auth import StaffSession
from backend.services.patients import validate_link
from backend.services.qr import render_qr
from backend.services.queue import issue_token



class SlotInput(Input):
    department_id: uuid.UUID
    starts_at: datetime
    capacity: int = Field(default=1, ge=1, le=20)


class BookingInput(Input):
    slot_id: uuid.UUID
    patient_id: uuid.UUID | None = None


class SelfInput(Input):
    request_id: uuid.UUID


class KioskInput(Input):
    department_id: uuid.UUID


def resolve(conn, key, lock=False):
    if not valid_private_key(key):
        raise ServiceError(404, 'Check-in link not found.')
    row = conn.execute(
        """SELECT a.id,a.reference,a.status,a.token_id,a.attendance_outcome,a.patient_id,s.starts_at,s.department_id,d.name AS department,d.is_active
    FROM appointments a JOIN appointment_slots s ON s.id=a.slot_id JOIN departments d ON d.id=s.department_id
    WHERE a.public_key=%s"""
        + (' FOR UPDATE OF a' if lock else ''),
        (key,),
    ).fetchone()
    if row:
        return 'appointment', row
    row = conn.execute(
        'SELECT k.*,d.name AS department,d.is_active FROM checkin_kiosks k JOIN departments d ON d.id=k.department_id WHERE k.public_key=%s'
        + (' FOR UPDATE OF k' if lock else ''),
        (key,),
    ).fetchone()
    if not row:
        raise ServiceError(404, 'Check-in link not found.')
    if row['revoked_at'] or row['expires_at'] <= datetime.now(TZ):
        raise ServiceError(
            410, 'This QR code has expired. Ask reception for today’s code.'
        )
    return 'walkin', row


async def events(
    settings: Settings,
    channel: str,
    is_disconnected: Callable[[], Awaitable[bool]],
    staff_session: StaffSession | None = None,
) -> AsyncIterator[str]:
    """Keep the LISTEN connection scoped to this stream and release it on exit."""
    async with await psycopg.AsyncConnection.connect(
        settings.database_url, autocommit=True, **connection_parameters(settings)
    ) as conn:
        await conn.execute(sql.SQL('LISTEN {}').format(sql.Identifier(channel)))
        yield 'retry: 2000\nevent: ready\ndata: {}\n\n'
        started = time.monotonic()
        while time.monotonic() - started < 50:
            if await is_disconnected():
                break
            if staff_session:
                if datetime.now(TZ) >= staff_session.get(
                    'access_expires_at', staff_session['expires_at']
                ):
                    break
                cursor = await conn.execute(
                    'SELECT 1 FROM auth_sessions s JOIN users u ON u.id=s.user_id '
                    'WHERE s.id=%s AND s.user_id=%s AND s.auth_mode=%s AND s.expires_at>now() AND u.is_active '
                    "AND EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_code=u.role "
                    "AND rp.permission_code IN ('queue:read','performance:read'))",
                    (
                        staff_session['session_id'],
                        staff_session['id'],
                        'jwt' if settings.jwt else 'opaque',
                    ),
                )
                if not await cursor.fetchone():
                    break
            async for notification in conn.notifies(timeout=8, stop_after=1):
                yield 'event: change\ndata: {}\n\n'
            yield ': heartbeat\n\n'


def slots(settings, day, department, user):
    authorize(user, 'appointment:read')
    with connection(settings) as conn:
        return conn.execute(
            """SELECT s.*,d.name AS department,count(a.id) FILTER (WHERE a.status!='cancelled') AS booked
        FROM appointment_slots s JOIN departments d ON d.id=s.department_id LEFT JOIN appointments a ON a.slot_id=s.id
        WHERE (s.starts_at AT TIME ZONE 'Asia/Colombo')::date=%s AND (%s::uuid IS NULL OR s.department_id=%s)
        GROUP BY s.id,d.name ORDER BY s.starts_at,d.name""",
            (day, department, department),
        ).fetchall()


def create_slot(settings, body, user):
    authorize(user, 'appointment:update')
    now = datetime.now(TZ)
    if body.starts_at.tzinfo is None or not now < body.starts_at <= now + timedelta(
        days=90
    ):
        raise ServiceError(422, 'Choose a future slot within 90 days, with a timezone.')
    local = body.starts_at.astimezone(TZ)
    if local.minute not in (0, 30) or local.second or local.microsecond:
        raise ServiceError(422, 'Slots start on the hour or half hour in Asia/Colombo.')
    with connection(settings) as conn:
        if not conn.execute(
            'SELECT 1 FROM departments WHERE id=%s AND is_active', (body.department_id,)
        ).fetchone():
            raise ServiceError(404, 'Department unavailable.')
        row = conn.execute(
            'INSERT INTO appointment_slots(department_id,starts_at,capacity,created_by) VALUES(%s,%s,%s,%s) ON CONFLICT(department_id,starts_at) DO NOTHING RETURNING *',
            (body.department_id, body.starts_at, body.capacity, user['id']),
        ).fetchone()
        if not row:
            raise ServiceError(409, 'A slot already exists at that time.')
        audit(conn, user, 'create_appointment_slot', 'appointment_slot', row['id'])
        return row


def appointments(settings, day, user):
    authorize(user, 'appointment:read')
    with connection(settings) as conn:
        rows = conn.execute(
            """SELECT a.*,s.starts_at,d.name AS department FROM appointments a
        JOIN appointment_slots s ON s.id=a.slot_id JOIN departments d ON d.id=s.department_id
        WHERE (s.starts_at AT TIME ZONE 'Asia/Colombo')::date=%s ORDER BY s.starts_at,a.created_at""",
            (day,),
        ).fetchall()
        for row in rows:
            row.pop('patient_id')
        return rows


def book(settings, body, user):
    authorize(user, 'appointment:book')
    with connection(settings) as conn:
        validate_link(conn, body.patient_id)
        slot = conn.execute(
            'SELECT s.*,d.is_active FROM appointment_slots s JOIN departments d ON d.id=s.department_id WHERE s.id=%s FOR UPDATE OF s',
            (body.slot_id,),
        ).fetchone()
        if not slot or not slot['is_active']:
            raise ServiceError(404, 'Slot unavailable.')
        if slot['starts_at'] <= datetime.now(TZ):
            raise ServiceError(409, 'This slot has already started.')
        count = conn.execute(
            "SELECT count(*) AS n FROM appointments WHERE slot_id=%s AND status!='cancelled'",
            (body.slot_id,),
        ).fetchone()['n']
        if count >= slot['capacity']:
            raise ServiceError(409, 'This slot is full. Choose another time.')
        try:
            row = conn.execute(
                'INSERT INTO appointments(slot_id,reference,public_key,created_by,patient_id) '
                'VALUES(%s,%s,%s,%s,%s) RETURNING *',
                (
                    body.slot_id,
                    'APT-' + secrets.token_hex(5).upper(),
                    secrets.token_urlsafe(32),
                    user['id'],
                    body.patient_id,
                ),
            ).fetchone()
        except UniqueViolation as exc:
            if exc.diag.constraint_name == 'appointments_one_patient_per_slot':
                raise ServiceError(
                    409, 'This patient already has a booking for this slot.'
                ) from exc
            raise
        from backend.automation import send

        send(
            conn,
            slot['department_id'],
            'appointment',
            'booking_confirmation',
            'Your arrival slot is booked for '
            + slot['starts_at'].astimezone(TZ).strftime('%d %b %Y, %H:%M')
            + ' Colombo time. Confirm attendance through this private page.',
            'booked:' + str(row['id']),
            appointment=row['id'],
        )
        audit(conn, user, 'book_appointment', 'appointment', row['id'])
        row.pop('patient_id')
        return row


def cancel(settings, appointment_id, user):
    authorize(user, 'appointment:update')
    with connection(settings) as conn:
        row = conn.execute(
            "UPDATE appointments SET status='cancelled' WHERE id=%s AND status='booked' RETURNING *",
            (appointment_id,),
        ).fetchone()
        if not row:
            raise ServiceError(409, 'Only booked appointments can be cancelled.')
        audit(conn, user, 'cancel_appointment', 'appointment', row['id'])
        from backend.automation import send

        dep = conn.execute(
            'SELECT department_id FROM appointment_slots WHERE id=%s', (row['slot_id'],)
        ).fetchone()['department_id']
        send(
            conn,
            dep,
            'appointment',
            'booking_cancelled',
            'Reception cancelled this appointment. Please contact the clinic to arrange another visit.',
            'cancelled:' + str(row['id']),
            appointment=row['id'],
        )
        row.pop('patient_id')
        return row


def kiosks(settings, user):
    authorize(user, 'kiosk:manage')
    with connection(settings) as conn:
        return conn.execute(
            'SELECT k.*,d.name AS department FROM checkin_kiosks k JOIN departments d ON d.id=k.department_id WHERE expires_at>now() AND revoked_at IS NULL ORDER BY d.name'
        ).fetchall()


def create_kiosk(settings, body, user):
    authorize(user, 'kiosk:manage')
    with connection(settings) as conn:
        lock_queue_writes(conn)
        if not conn.execute(
            'SELECT 1 FROM departments WHERE id=%s AND is_active', (body.department_id,)
        ).fetchone():
            raise ServiceError(404, 'Department unavailable.')
        existing = conn.execute(
            'SELECT * FROM checkin_kiosks WHERE department_id=%s AND expires_at>now() AND revoked_at IS NULL',
            (body.department_id,),
        ).fetchone()
        if existing:
            return existing
        expires = (datetime.now(TZ) + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        row = conn.execute(
            'INSERT INTO checkin_kiosks(department_id,public_key,expires_at,created_by) VALUES(%s,%s,%s,%s) RETURNING *',
            (body.department_id, secrets.token_urlsafe(32), expires, user['id']),
        ).fetchone()
        audit(conn, user, 'create_checkin_qr', 'checkin_kiosk', row['id'])
        return row


def revoke(settings, kiosk_id, user):
    authorize(user, 'kiosk:manage')
    with connection(settings) as conn:
        row = conn.execute(
            'UPDATE checkin_kiosks SET revoked_at=now() WHERE id=%s RETURNING id',
            (kiosk_id,),
        ).fetchone()
        if not row:
            raise ServiceError(404, 'QR code not found.')
        audit(conn, user, 'revoke_checkin_qr', 'checkin_kiosk', row['id'])
        return {'ok': True}


def info(settings, key):
    with connection(settings) as conn:
        kind, row = resolve(conn, key)
        return dict(
            kind=kind,
            department=row['department'],
            reference=row.get('reference'),
            starts_at=row.get('starts_at'),
            status=row.get('status', 'open'),
            active=row['is_active'] and not row.get('attendance_outcome'),
        )


def qr(settings, key, origin):
    if origin not in settings.origins:
        raise ServiceError(422, 'Use a configured clinic URL.')
    with connection(settings) as conn:
        resolve(conn, key)
    return render_qr(origin + '/self-checkin/' + key)


def self_checkin(settings, key, body):
    with connection(settings) as conn:
        # Same lock order as normal check-in; one transaction issues and links the token.
        lock_queue_writes(conn)
        kind, row = resolve(conn, key, lock=True)
        if not row['is_active']:
            raise ServiceError(409, 'Department unavailable. Contact reception.')
        token_id = row.get('token_id')
        if kind == 'appointment':
            if row['status'] == 'cancelled':
                raise ServiceError(409, 'This appointment was cancelled.')
            if not token_id and not row['starts_at'] - timedelta(
                minutes=30
            ) <= datetime.now(TZ) < row['starts_at'] + timedelta(minutes=30):
                raise ServiceError(
                    409,
                    'Check-in opens 30 minutes before your slot and closes 30 minutes after it starts.',
                )
        else:
            prior = conn.execute(
                'SELECT token_id FROM self_checkins WHERE kiosk_id=%s AND request_id=%s',
                (row['id'], body.request_id),
            ).fetchone()
            token_id = prior['token_id'] if prior else None
            count = conn.execute(
                "SELECT count(*) AS n FROM self_checkins c JOIN queue_tokens t ON t.id=c.token_id WHERE c.kiosk_id=%s AND t.check_in_at>now()-interval '1 minute'",
                (row['id'],),
            ).fetchone()['n']
            if not token_id and count >= 20:
                raise ServiceError(
                    429,
                    'Many arrivals just checked in. Please try again in a minute.',
                    headers={'Retry-After': '60'},
                )
        if token_id:
            token = conn.execute(
                'SELECT public_key FROM queue_tokens WHERE id=%s', (token_id,)
            ).fetchone()
        else:
            token = issue_token(
                conn, row['department_id'], patient_id=row.get('patient_id')
            )
            if kind == 'appointment':
                conn.execute(
                    "UPDATE appointments SET status='checked_in',token_id=%s WHERE id=%s",
                    (token['id'], row['id']),
                )
            else:
                conn.execute(
                    'INSERT INTO self_checkins(kiosk_id,request_id,token_id) VALUES(%s,%s,%s)',
                    (row['id'], body.request_id, token['id']),
                )
        return {'patient_key': token['public_key']}


def patient_event_channel(settings, key):
    if not valid_private_key(key):
        raise ServiceError(404, 'Token not found.')
    with connection(settings) as conn:
        row = conn.execute(
            'SELECT department_id FROM queue_tokens WHERE public_key=%s', (key,)
        ).fetchone()
        if not row:
            raise ServiceError(404, 'Token not found.')
    return 'queuesense_' + row['department_id'].hex

"""Application use cases for clinic operations."""

from datetime import date, timedelta
from uuid import UUID

from psycopg.errors import ExclusionViolation

from backend.core.authorization import authorize
from backend.core.config import CLINIC_TIMEZONE as TZ
from backend.core.config import Settings
from backend.core.errors import ServiceError
from backend.core.security import HASHER
from backend.database import DatabaseConnection, Row, connection, read_snapshot
from backend.repositories import clinicians
from backend.repositories.audit import audit
from backend.schemas.product import ScheduleInput
from backend.services.auth import StaffSession
from backend.services.metrics import filters


def station(conn: DatabaseConnection, staff_id: UUID, user: StaffSession) -> Row:
    row = clinicians.lock_station(conn, staff_id)
    if not row:
        raise ServiceError(404, 'Active clinician not found.')
    if user['role'] == 'doctor' and (
        row['staff_type'] != 'doctor' or str(row['user_id']) != user['id']
    ):
        raise ServiceError(
            403, 'Doctors can only manage their assigned clinician queue.'
        )
    return row


def active_staff(conn, department_id):
    return conn.execute(
        "SELECT count(*) AS count FROM staff st LEFT JOIN LATERAL (SELECT status,changed_at FROM staff_availability WHERE staff_id=st.id ORDER BY changed_at DESC LIMIT 1) a ON true WHERE st.department_id=%s AND st.is_active AND a.status IN ('available','busy') AND (a.changed_at AT TIME ZONE 'Asia/Colombo')::date=(now() AT TIME ZONE 'Asia/Colombo')::date",
        (department_id,),
    ).fetchone()['count']


def service_estimate(conn, department_id):
    return float(
        conn.execute(
            'SELECT coalesce(avg(service_minutes),12) AS minutes FROM (SELECT extract(epoch FROM(completed_at-service_start_at))/60 AS service_minutes FROM queue_tokens WHERE department_id=%s AND completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT 30) recent',
            (department_id,),
        ).fetchone()['minutes']
    )


def departments(settings):
    with connection(settings) as conn:
        return conn.execute('SELECT * FROM departments ORDER BY name').fetchall()


def staff(settings, user: StaffSession):
    authorize(user, 'doctor:read')
    with connection(settings) as conn:
        rows = conn.execute(
            "SELECT st.*,d.name AS department,coalesce(a.status,'offline') AS availability,a.changed_at FROM staff st JOIN departments d ON d.id=st.department_id LEFT JOIN LATERAL(SELECT status,changed_at FROM staff_availability WHERE staff_id=st.id AND (changed_at AT TIME ZONE 'Asia/Colombo')::date=(now() AT TIME ZONE 'Asia/Colombo')::date ORDER BY changed_at DESC LIMIT 1)a ON true ORDER BY d.name,st.display_name"
        ).fetchall()
        if 'users:manage' not in user['permissions']:
            for row in rows:
                if str(row['user_id']) != user['id']:
                    row['user_id'] = None
        return rows


def users(settings, user):
    authorize(user, 'users:manage')
    with connection(settings) as conn:
        return conn.execute(
            'SELECT id,email,role,is_active,created_at FROM users ORDER BY email'
        ).fetchall()


def create_user(settings, body, user):
    authorize(user, 'users:manage')
    with connection(settings) as conn:
        if conn.execute(
            'SELECT 1 FROM users WHERE email=%s', (body.email.lower(),)
        ).fetchone():
            raise ServiceError(409, 'An account with this email already exists.')
        row = conn.execute(
            'INSERT INTO users(email,password_hash,role) VALUES(%s,%s,%s) RETURNING id,email,role',
            (body.email.lower(), HASHER.hash(body.password), body.role),
        ).fetchone()
        audit(conn, user, 'create_user', 'user', row['id'])
        return row


def update_user(settings, user_id, body, user):
    authorize(user, 'users:manage')
    if str(user_id) == user['id']:
        raise ServiceError(409, 'You cannot change your own access.')
    with connection(settings) as conn:
        row = conn.execute(
            'UPDATE users SET role=%s,is_active=%s WHERE id=%s RETURNING id',
            (body.role, body.is_active, user_id),
        ).fetchone()
        if not row:
            raise ServiceError(404, 'User not found.')
        conn.execute('DELETE FROM auth_sessions WHERE user_id=%s', (user_id,))
        audit(conn, user, 'update_access', 'user', user_id)
    return {'ok': True}


def add_department(settings, body, user):
    authorize(user, 'department:manage')
    with connection(settings) as conn:
        if conn.execute(
            'SELECT 1 FROM departments WHERE code=%s OR name=%s', (body.code, body.name)
        ).fetchone():
            raise ServiceError(409, 'Department code or name already exists.')
        row = conn.execute(
            'INSERT INTO departments(code,name,location,queue_threshold) VALUES(%s,%s,%s,%s) RETURNING *',
            (body.code, body.name, body.location, body.queue_threshold),
        ).fetchone()
        audit(conn, user, 'create_department', 'department', row['id'])
        return row


def update_department(settings, department_id, body, user):
    authorize(user, 'department:manage')
    with connection(settings) as conn:
        if conn.execute(
            'SELECT 1 FROM departments WHERE (code=%s OR name=%s) AND id<>%s',
            (body.code, body.name, department_id),
        ).fetchone():
            raise ServiceError(409, 'Department name or code already exists.')
        row = conn.execute(
            'UPDATE departments SET code=%s,name=%s,location=%s,queue_threshold=%s WHERE id=%s RETURNING id',
            (body.code, body.name, body.location, body.queue_threshold, department_id),
        ).fetchone()
        if not row:
            raise ServiceError(404, 'Department not found.')
        audit(conn, user, 'update_department', 'department', department_id)
    return {'ok': True}


def add_staff(settings, body, user):
    authorize(user, 'doctor:manage')
    with connection(settings) as conn:
        if not conn.execute(
            'SELECT 1 FROM departments WHERE id=%s', (body.department_id,)
        ).fetchone():
            raise ServiceError(404, 'Department not found.')
        if body.user_id and (
            not conn.execute(
                "SELECT 1 FROM users WHERE id=%s AND role='doctor'", (body.user_id,)
            ).fetchone()
            or conn.execute(
                'SELECT 1 FROM staff WHERE user_id=%s', (body.user_id,)
            ).fetchone()
        ):
            raise ServiceError(409, 'Choose an unassigned doctor account.')
        row = conn.execute(
            "INSERT INTO staff(department_id,display_name,staff_type,user_id) VALUES(%s,%s,'doctor',%s) RETURNING *",
            (body.department_id, body.display_name, body.user_id),
        ).fetchone()
        audit(conn, user, 'create_staff', 'staff', row['id'])
        return row


def schedules(settings: Settings, start: date, end: date) -> list[Row]:
    filters(start, end)
    with connection(settings) as conn:
        return clinicians.schedules_between(conn, start, end)


def schedule(
    settings: Settings, staff_id: UUID, body: ScheduleInput, user: StaffSession
):
    authorize(user, 'doctor:manage')
    if (
        not body.start_at.tzinfo
        or not body.end_at.tzinfo
        or body.end_at <= body.start_at
        or body.end_at - body.start_at > timedelta(hours=16)
    ):
        raise ServiceError(
            422, 'Use timezone-aware dates with a positive shift up to 16 hours.'
        )
    with connection(settings) as conn:
        station(conn, staff_id, user)
        if clinicians.has_schedule_overlap(conn, staff_id, body.start_at, body.end_at):
            raise ServiceError(409, 'Schedule overlaps an existing shift.')
        try:
            schedule_id = clinicians.insert_schedule(
                conn,
                staff_id,
                body.start_at.astimezone(TZ).date(),
                body.start_at,
                body.end_at,
            )
        except ExclusionViolation as exc:
            if exc.diag.constraint_name == 'staff_schedules_no_overlap':
                raise ServiceError(409, 'Schedule overlaps an existing shift.') from exc
            raise
        audit(conn, user, 'schedule_staff', 'staff_schedule', schedule_id)
    return {'ok': True}


def audit_log(settings, search, start, end, entity_id, offset, user):
    authorize(user, 'audit:read')
    if start and end:
        filters(start, end)
    with connection(settings) as conn:
        return conn.execute(
            """SELECT a.*,u.email FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id
        WHERE (a.action ILIKE %s OR coalesce(u.email,'') ILIKE %s OR a.entity_type ILIKE %s)
        AND (%s::date IS NULL OR (a.created_at AT TIME ZONE 'Asia/Colombo')::date>=%s)
        AND (%s::date IS NULL OR (a.created_at AT TIME ZONE 'Asia/Colombo')::date<=%s)
        AND (%s::uuid IS NULL OR a.entity_id=%s)
        ORDER BY a.created_at DESC,a.id DESC LIMIT 200 OFFSET %s""",
            ('%' + search + '%',) * 3
            + (start, start, end, end, entity_id, entity_id, offset),
        ).fetchall()


def list_doctors(settings: Settings, query):
    with read_snapshot(settings) as conn:
        return clinicians.doctors_page(conn, query)


def get_doctor(settings: Settings, doctor_id: UUID):
    with connection(settings) as conn:
        row = clinicians.doctor(conn, doctor_id)
        if not row:
            raise ServiceError(404, 'Doctor not found.')
        return row


def doctor_schedule(settings: Settings, doctor_id: UUID, query):
    filters(query.start, query.end)
    with read_snapshot(settings) as conn:
        if not clinicians.doctor(conn, doctor_id):
            raise ServiceError(404, 'Doctor not found.')
        return clinicians.doctor_schedule(conn, doctor_id, query)

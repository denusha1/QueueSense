"""Application use cases for queue operations."""

import secrets
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.errors import UniqueViolation

from backend.core.authorization import authorize, queue_doctor
from backend.core.config import CLINIC_TIMEZONE as TZ
from backend.core.config import Settings
from backend.core.errors import ServiceError
from backend.core.security import valid_private_key
from backend.database import DatabaseConnection, Row, connection, read_snapshot
from backend.planning import eligible
from backend.repositories import clinicians
from backend.repositories import queue as repository
from backend.repositories.audit import audit
from backend.schemas.product import Availability, Change, StaffCheckIn
from backend.services.auth import StaffSession
from backend.services.clinic import station
from backend.services.patients import validate_link
from backend.services.qr import render_qr
from backend.services.queue_views import decorate_staff_queue_rows

TRANSITIONS = {
    'waiting': ['called', 'cancelled'],
    'called': ['in_service', 'cancelled', 'no_show'],
    'in_service': ['completed'],
}


def issue_token(
    conn: DatabaseConnection,
    department_id: UUID,
    user: StaffSession | None = None,
    requirements: Mapping[str, Any] | None = None,
    *,
    patient_id: UUID | None = None,
) -> Row:
    """Issue a token within an existing transaction for both staff and QR arrivals."""
    repository.lock_queue_writes(conn)
    dep = conn.execute(
        'SELECT * FROM departments WHERE id=%s AND is_active', (department_id,)
    ).fetchone()
    if not dep:
        raise ServiceError(404, 'Department unavailable.')
    validate_link(conn, patient_id)
    requirements = requirements or {}
    preferred = requirements.get('preferred_staff_id')
    if preferred:
        doctor = conn.execute(
            "SELECT * FROM staff WHERE id=%s AND department_id=%s AND is_active AND staff_type='doctor'",
            (preferred, department_id),
        ).fetchone()
        if not doctor:
            raise ServiceError(422, 'Choose an active doctor in this department.')
        if requirements.get('continuity_required') and not eligible(
            doctor, requirements
        ):
            raise ServiceError(
                422,
                'The preferred doctor does not support the required service or language.',
            )
    now = datetime.now(ZoneInfo(dep['timezone']))
    session = repository.open_session(conn, dep['id'], now)

    if session['closed_at']:
        raise ServiceError(409, 'Today’s session has been closed.')
    number = repository.next_token_number(conn, session['id'])
    try:
        row = repository.insert_token(
            conn,
            (
                session['id'],
                dep['id'],
                number,
                'SYN-' + secrets.token_hex(8).upper(),
                now,
                secrets.token_urlsafe(32),
                requirements.get('service_type', 'general_consultation'),
                requirements.get('required_language'),
                preferred,
                requirements.get('continuity_required', False),
                requirements.get('priority_class', 'standard'),
                requirements.get('priority_reason', ''),
                patient_id,
            ),
        )
    except UniqueViolation as exc:
        if exc.diag.constraint_name == 'queue_tokens_one_active_patient_per_session':
            raise ServiceError(
                409,
                'This patient already has an active token for this department today.',
            ) from exc
        raise
    repository.record_event(conn, row, None, 'check_in', now)
    audit(
        conn,
        user,
        'check_in',
        'queue_token',
        row['id'],
        {
            'status': 'waiting',
            'department_id': str(dep['id']),
            'priority_class': row['priority_class'],
            'priority_reason': row['priority_reason'],
        },
        actor_type='staff' if user else 'patient',
    )
    row['code'] = dep['code']
    from backend.services.prediction import predict_for_token

    row['prediction'] = predict_for_token(conn, row)
    return row


def transition(
    conn: DatabaseConnection, token_id: UUID, body: Change, user: StaffSession,
    *, call_next_claim: bool = False,
) -> Row:
    repository.lock_queue_writes(conn)
    token = repository.lock_token(conn, token_id)
    if not token:
        raise ServiceError(404, 'Token not found.')
    doctor_id = queue_doctor(user)
    if doctor_id and not (
        (call_next_claim and token['staff_id'] is None and body.status == 'called')
        or repository.staff_queue_record(conn, token_id, doctor_id)
    ):
        raise ServiceError(404, 'Token not found.')
    if body.status not in TRANSITIONS.get(token['status'], []):
        raise ServiceError(409, 'This queue transition is not allowed.')
    staff_id = body.staff_id if body.status == 'called' else token['staff_id']
    if doctor_id and staff_id is None:
        raise ServiceError(403, 'An assigned clinician is required.')
    if staff_id:
        clinician = station(conn, staff_id, user)
        if clinician['department_id'] != token['department_id']:
            raise ServiceError(409, 'Clinician belongs to another department.')
    if body.status == 'called':
        if staff_id and not eligible(clinician, token):
            raise ServiceError(
                409,
                'This doctor does not match the visit’s service, language or continuity requirements.',
            )
        if not staff_id:
            raise ServiceError(422, 'Choose a clinician to call this token.')
        availability = clinicians.latest_availability_today(conn, staff_id)
        if not availability or availability['status'] != 'available':
            raise ServiceError(409, 'Set this clinician to available first.')
        if repository.active_token_at_station(conn, staff_id):
            raise ServiceError(409, 'Clinician is serving another token.')
    now = datetime.now(TZ)
    field = {
        'called': 'called_at',
        'in_service': 'service_start_at',
        'completed': 'completed_at',
        'cancelled': 'ended_at',
        'no_show': 'ended_at',
    }[body.status]
    values = {'status': body.status, field: now, 'staff_id': staff_id}
    if body.status == 'completed':
        values['ended_at'] = now

    row = repository.update_token(conn, token_id, values)
    event = 'service_start' if body.status == 'in_service' else body.status
    repository.record_event(conn, row, staff_id, event, now)
    if staff_id and body.status in ('called', 'completed', 'cancelled', 'no_show'):
        conn.execute(
            'INSERT INTO staff_availability(staff_id,status,changed_at) VALUES(%s,%s,%s)',
            (staff_id, 'busy' if body.status == 'called' else 'available', now),
        )
    audit(
        conn,
        user,
        body.status,
        'queue_token',
        token_id,
        {
            'from_status': token['status'],
            'to_status': body.status,
            'staff_id': str(staff_id) if staff_id else None,
        },
    )
    private_fields = {'public_key', 'patient_id'}
    if doctor_id:
        private_fields.update({'priority_reason', 'synthetic_patient_id', 'source'})
    return {key: value for key, value in row.items() if key not in private_fields}


def live(settings: Settings, department: UUID | None, user: StaffSession):
    authorize(user, 'queue:read')
    doctor_id = queue_doctor(user)
    with connection(settings) as conn:
        rows = decorate_staff_queue_rows(
            conn, repository.live_tokens(conn, department, doctor_id), doctor_id
        )
        return dict(tokens=rows, as_of=datetime.now(TZ), limit=500)


def checkin(settings: Settings, body: StaffCheckIn, user: StaffSession) -> Row:
    authorize(user, 'queue:create')
    with connection(settings) as conn:
        token = issue_token(
            conn,
            body.department_id,
            user,
            body.model_dump(exclude={'patient_id'}),
            patient_id=body.patient_id,
        )
        token.pop('patient_id')
        return token


def private_link(settings: Settings, token_id: UUID, user: StaffSession):
    authorize(user, 'queue:links')
    with connection(settings) as conn:
        row = repository.public_key(conn, token_id)
        if not row:
            raise ServiceError(404, 'Token not found.')
        return {'public_key': row['public_key']}


def change(settings: Settings, token_id: UUID, body: Change, user: StaffSession) -> Row:
    authorize(user, 'queue:update')
    with connection(settings) as conn:
        return transition(conn, token_id, body, user)


def call_next(settings: Settings, staff_id: UUID, user: StaffSession) -> Row:
    authorize(user, 'queue:update')
    with connection(settings) as conn:
        repository.lock_queue_writes(conn)
        clinician = station(conn, staff_id, user)
        candidates = repository.waiting_candidates(conn, clinician['department_id'])
        row = next((t for t in candidates if eligible(clinician, t)), None)
        if not row:
            raise ServiceError(409, 'No eligible patients waiting for this doctor.')
        return transition(
            conn, row['id'], Change(status='called', staff_id=staff_id), user,
            call_next_claim=True,
        )


def availability(
    settings: Settings, staff_id: UUID, body: Availability, user: StaffSession
):
    authorize(user, 'queue:update')
    with connection(settings) as conn:
        repository.lock_queue_writes(conn)
        station(conn, staff_id, user)
        if repository.active_token_at_station(conn, staff_id):
            raise ServiceError(
                409, 'Finish the active token before changing availability.'
            )
        conn.execute(
            'INSERT INTO staff_availability(staff_id,status,changed_at) VALUES(%s,%s,now())',
            (staff_id, body.status),
        )
        audit(conn, user, 'availability:' + body.status, 'staff', staff_id)
        return {'ok': True}


def close_session(settings: Settings, department_id: UUID, user: StaffSession):
    authorize(user, 'queue:close')
    with connection(settings) as conn:
        repository.lock_queue_writes(conn)
        row = conn.execute(
            "SELECT id FROM queue_sessions WHERE department_id=%s AND service_date=(now() AT TIME ZONE 'Asia/Colombo')::date",
            (department_id,),
        ).fetchone()
        if not row:
            raise ServiceError(404, 'No session today.')
        if conn.execute(
            "SELECT 1 FROM queue_tokens WHERE session_id=%s AND status IN ('waiting','called','in_service')",
            (row['id'],),
        ).fetchone():
            raise ServiceError(409, 'Complete or cancel all active tokens first.')
        conn.execute(
            'UPDATE queue_sessions SET closed_at=coalesce(closed_at,now()) WHERE id=%s',
            (row['id'],),
        )
        audit(conn, user, 'close_session', 'queue_session', row['id'])
        return {'ok': True}


def tracking_qr(settings: Settings, key: str, origin: str) -> str:
    if origin not in settings.origins:
        raise ServiceError(422, 'Use a configured clinic URL.')
    if not valid_private_key(key):
        raise ServiceError(404, 'Token not found.')
    with connection(settings) as conn:
        if not conn.execute(
            'SELECT 1 FROM queue_tokens WHERE public_key=%s', (key,)
        ).fetchone():
            raise ServiceError(404, 'Token not found.')
    return render_qr(origin + '/patient/' + key)


def patient(settings: Settings, key: str):
    if not valid_private_key(key):
        raise ServiceError(404, 'Token not found.')
    with connection(settings) as conn:
        row = repository.patient_token(conn, key)
        if not row:
            raise ServiceError(404, 'Token not found.')
        from backend.services.prediction import live_predictions

        prediction = (
            live_predictions(conn, row['department_id']).get(str(row['id']), {})
            if row['status'] == 'waiting'
            else {}
        )
        actual = (
            round(
                (row['service_start_at'] - row['check_in_at']).total_seconds() / 60, 1
            )
            if row['service_start_at']
            else None
        )
        return dict(
            token=f'{row["code"]}-{row["token_no"]:03}',
            department=row['department'],
            status=row['status'],
            priority_class=row['priority_class'],
            position=prediction.get('position'),
            patients_ahead=prediction.get('patients_ahead'),
            estimated_wait=prediction.get('minutes'),
            prediction_source=prediction.get('source'),
            explanation=prediction.get('explanation'),
            initial_prediction=row['initial_wait_minutes'],
            actual_wait=actual,
            prediction_error=round(actual - row['initial_wait_minutes'], 1)
            if actual is not None and row['initial_wait_minutes'] is not None
            else None,
            notice=prediction.get(
                'reason', 'Your private token shows recorded queue progress.'
            ),
        )


def list_records(settings: Settings, query, user: StaffSession):
    authorize(user, 'queue:read')
    with read_snapshot(settings) as conn:
        return repository.staff_queue_page(conn, query, queue_doctor(user))


def get_record(settings: Settings, token_id: UUID, user: StaffSession):
    authorize(user, 'queue:read')
    with connection(settings) as conn:
        row = repository.staff_queue_record(conn, token_id, queue_doctor(user))
        if not row:
            raise ServiceError(404, 'Token not found.')
        return row


def history(settings: Settings, token_id: UUID, limit: int, offset: int, user: StaffSession):
    authorize(user, 'queue:read')
    with read_snapshot(settings) as conn:
        if not repository.staff_queue_record(conn, token_id, queue_doctor(user)):
            raise ServiceError(404, 'Token not found.')
        return repository.staff_queue_history(conn, token_id, limit, offset)

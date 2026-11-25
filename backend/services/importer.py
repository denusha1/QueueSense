"""Bounded CSV import with per-row savepoints and sanitized rejections."""

import csv
import hashlib
import io
from datetime import datetime, timedelta

import psycopg

from backend.core.config import CLINIC_TIMEZONE
from backend.core.errors import ServiceError
from backend.repositories.queue import lock_queue_writes

REQUIRED = (
    'department',
    'token_no',
    'status',
    'check_in_at',
    'called_at',
    'service_start_at',
    'completed_at',
    'ended_at',
)
TIMESTAMP_FIELDS = REQUIRED[3:]


class InvalidRow(ValueError):
    """A CSV row is invalid. Messages supplied here contain no input values."""


def read_rows(text):
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')), strict=True)
        if (
            not reader.fieldnames
            or len(reader.fieldnames) != len(REQUIRED)
            or set(reader.fieldnames) != set(REQUIRED)
        ):
            raise ServiceError(
                422, 'CSV columns must be exactly: ' + ', '.join(REQUIRED)
            )
        rows = []
        for row in reader:
            if len(rows) == 5000:
                raise ServiceError(422, 'Import at most 5,000 rows per file.')
            rows.append(row)
    except csv.Error as exc:
        raise ServiceError(422, 'Malformed CSV file.') from exc
    if not rows:
        raise ServiceError(422, 'CSV contains no data rows.')
    return rows


def import_row(conn, row, departments, seen):
    if None in row or any(value is None for value in row.values()):
        raise InvalidRow('Column count differs from header.')
    department = departments.get(row['department'].strip().upper())
    if not department:
        raise InvalidRow('Unknown department code.')
    try:
        number = int(row['token_no'])
    except ValueError:
        raise InvalidRow('Token number must be an integer.') from None
    if not 0 < number <= 2_147_483_647:
        raise InvalidRow('Token number is outside the supported positive range.')

    try:
        stamps = {
            field: datetime.fromisoformat(row[field]) if row[field].strip() else None
            for field in TIMESTAMP_FIELDS
        }
        arrival = stamps['check_in_at']
        if not arrival or any(
            value and value.utcoffset() is None for value in stamps.values()
        ):
            raise InvalidRow(
                'Arrival is required and timestamps must include timezone offsets.'
            )
        day = arrival.astimezone(CLINIC_TIMEZONE).date()
    except InvalidRow:
        raise
    except (ValueError, OverflowError):
        raise InvalidRow(
            'Use valid ISO 8601 timestamps with timezone offsets.'
        ) from None
    if day >= datetime.now(CLINIC_TIMEZONE).date():
        raise InvalidRow('Historical imports must precede today.')

    status = row['status'].strip()
    if status not in ('completed', 'cancelled', 'no_show'):
        raise InvalidRow('Historical rows must be completed, cancelled or no_show.')
    key = hashlib.sha256(f'{department}:{day}:{number}'.encode()).hexdigest()
    if (
        key in seen
        or conn.execute(
            'SELECT 1 FROM queue_tokens WHERE import_key=%s', (key,)
        ).fetchone()
    ):
        return None, False
    session = conn.execute(
        'SELECT id FROM queue_sessions WHERE department_id=%s AND service_date=%s',
        (department, day),
    ).fetchone()
    if (
        session
        and conn.execute(
            'SELECT 1 FROM queue_tokens WHERE session_id=%s AND token_no=%s',
            (session['id'], number),
        ).fetchone()
    ):
        return None, False

    last = max(value for value in stamps.values() if value)
    if session:
        conn.execute(
            'UPDATE queue_sessions SET closed_at=greatest(closed_at,%s) WHERE id=%s',
            (last, session['id']),
        )
    else:
        session = conn.execute(
            'INSERT INTO queue_sessions(department_id,service_date,opened_at,closed_at) '
            'VALUES(%s,%s,%s,%s) RETURNING id',
            (
                department,
                day,
                datetime.combine(day, datetime.min.time(), CLINIC_TIMEZONE),
                last,
            ),
        ).fetchone()

    clinician = None
    if status in ('completed', 'no_show') or stamps['called_at']:
        clinician_row = conn.execute(
            'SELECT id FROM staff WHERE department_id=%s ORDER BY id LIMIT 1',
            (department,),
        ).fetchone()
        if not clinician_row:
            raise InvalidRow(
                'Department needs a demo clinician before importing service records.'
            )
        clinician = clinician_row['id']
    token = conn.execute(
        'INSERT INTO queue_tokens(session_id,department_id,staff_id,token_no,synthetic_patient_id,'
        'status,check_in_at,called_at,service_start_at,completed_at,ended_at,import_key) '
        'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',
        (
            session['id'],
            department,
            clinician,
            number,
            'SYN-IMPORT-' + key[:12].upper(),
            status,
            *stamps.values(),
            key,
        ),
    ).fetchone()
    event_map = {
        'check_in_at': 'check_in',
        'called_at': 'called',
        'service_start_at': 'service_start',
        'completed_at': 'completed',
    }
    if status != 'completed':
        event_map['ended_at'] = status
    for field, event in event_map.items():
        if stamps[field]:
            conn.execute(
                'INSERT INTO service_events(token_id,department_id,staff_id,event_type,event_time) '
                'VALUES(%s,%s,%s,%s,%s)',
                (
                    token['id'],
                    department,
                    None if event == 'check_in' else clinician,
                    event,
                    stamps[field],
                ),
            )
    return key, last - arrival > timedelta(hours=4)


def import_csv(conn, text, dry_run):
    rows = read_rows(text)
    lock_queue_writes(conn)
    departments = {
        row['code']: row['id']
        for row in conn.execute('SELECT id,code FROM departments').fetchall()
    }
    seen = set()
    accepted = duplicates = 0
    errors, warnings = [], []
    with conn.transaction(force_rollback=dry_run):
        for index, row in enumerate(rows, 2):
            try:
                with conn.transaction():
                    key, long_visit = import_row(conn, row, departments, seen)
            except InvalidRow as exc:
                errors.append({'row': index, 'message': str(exc)})
                continue
            except (
                psycopg.IntegrityError,
                psycopg.DataError,
                psycopg.errors.RaiseException,
            ):
                errors.append(
                    {
                        'row': index,
                        'message': 'Invalid state, timestamp chronology, session or database reference.',
                    }
                )
                continue

            if key is None:
                duplicates += 1
            else:
                seen.add(key)
                accepted += 1
                if long_visit:
                    warnings.append(
                        {
                            'row': index,
                            'message': 'Duration exceeds four hours; retained for review.',
                        }
                    )

    return dict(
        dry_run=dry_run,
        total=len(rows),
        accepted=accepted,
        rejected=len(errors),
        duplicates=duplicates,
        errors=errors[:100],
        warnings=warnings[:100],
        note='Accepted rows can be imported; invalid rows are quarantined in this error summary. Synthetic service records are assigned to the first department demo clinician. No identifying fields are accepted.',
    )

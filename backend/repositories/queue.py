"""Queue persistence. Use cases own permissions, ordering policy, and transactions."""

from psycopg import sql

from backend.database import DatabaseConnection

LIVE_FIELDS = """
    SELECT t.id,t.department_id,t.staff_id,t.token_no,t.status,t.priority_class,t.priority_reason,
           t.initial_wait_minutes,t.initial_prediction_version,t.check_in_at,t.called_at,
           t.service_start_at,t.completed_at,d.code,d.name AS department,st.display_name AS clinician
"""
LIVE_JOINS = """
    FROM queue_tokens t JOIN queue_sessions s ON s.id=t.session_id
    JOIN departments d ON d.id=s.department_id LEFT JOIN staff st ON st.id=t.staff_id
"""
LIVE_FILTER = 's.service_date=(now() AT TIME ZONE d.timezone)::date AND (%s::uuid IS NULL OR d.id=%s)'
PRIORITY_ORDER = (
    "CASE t.priority_class WHEN 'expedited' THEN 0 ELSE 1 END,t.check_in_at,t.token_no"
)


def live_tokens(conn: DatabaseConnection, department):
    return conn.execute(
        LIVE_FIELDS
        + LIVE_JOINS
        + ' WHERE '
        + LIVE_FILTER
        + ' ORDER BY '
        + PRIORITY_ORDER
        + ' LIMIT 500',
        (department, department),
    ).fetchall()


def lock_queue_writes(conn: DatabaseConnection) -> None:
    conn.execute('SELECT pg_advisory_xact_lock(72419023)')


def lock_token(conn: DatabaseConnection, token_id):
    return conn.execute(
        'SELECT * FROM queue_tokens WHERE id=%s FOR UPDATE', (token_id,)
    ).fetchone()


def open_session(conn: DatabaseConnection, department, now):
    conn.execute(
        'INSERT INTO queue_sessions(department_id,service_date,opened_at) VALUES(%s,%s,%s) '
        'ON CONFLICT(department_id,service_date) DO NOTHING',
        (
            department,
            now.date(),
            now.replace(hour=0, minute=0, second=0, microsecond=0),
        ),
    )
    return conn.execute(
        'SELECT * FROM queue_sessions WHERE department_id=%s AND service_date=%s FOR UPDATE',
        (department, now.date()),
    ).fetchone()


def next_token_number(conn: DatabaseConnection, session_id) -> int:
    return conn.execute(
        'SELECT coalesce(max(token_no),0)+1 AS next FROM queue_tokens WHERE session_id=%s',
        (session_id,),
    ).fetchone()['next']


def insert_token(conn: DatabaseConnection, values):
    return conn.execute(
        'INSERT INTO queue_tokens(session_id,department_id,token_no,synthetic_patient_id,check_in_at,'
        'public_key,service_type,required_language,preferred_staff_id,continuity_required,'
        'priority_class,priority_reason,patient_id) '
        'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',
        values,
    ).fetchone()


def update_token(conn: DatabaseConnection, token_id, values):
    assignments = sql.SQL(',').join(
        sql.SQL('{}=%s').format(sql.Identifier(key)) for key in values
    )
    statement = sql.SQL('UPDATE queue_tokens SET {} WHERE id=%s RETURNING *').format(
        assignments
    )
    return conn.execute(statement, (*values.values(), token_id)).fetchone()


def record_event(conn: DatabaseConnection, token, staff_id, event, now) -> None:
    conn.execute(
        'INSERT INTO service_events(token_id,department_id,staff_id,event_type,event_time) '
        'VALUES(%s,%s,%s,%s,%s)',
        (token['id'], token['department_id'], staff_id, event, now),
    )


def waiting_candidates(conn: DatabaseConnection, department):
    return conn.execute(
        'SELECT t.* FROM queue_tokens t JOIN queue_sessions s ON s.id=t.session_id '
        "WHERE t.department_id=%s AND t.status='waiting' AND "
        "s.service_date=(now() AT TIME ZONE 'Asia/Colombo')::date ORDER BY "
        + PRIORITY_ORDER
        + ' FOR UPDATE OF t',
        (department,),
    ).fetchall()


def active_token_at_station(conn: DatabaseConnection, staff_id) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM queue_tokens WHERE staff_id=%s AND status IN ('called','in_service')",
            (staff_id,),
        ).fetchone()
        is not None
    )


def public_key(conn: DatabaseConnection, token_id):
    return conn.execute(
        'SELECT public_key FROM queue_tokens WHERE id=%s', (token_id,)
    ).fetchone()


def patient_token(conn: DatabaseConnection, key: str):
    return conn.execute(
        'SELECT t.id,t.session_id,t.department_id,t.token_no,t.status,t.priority_class,t.check_in_at,'
        't.service_start_at,t.initial_wait_minutes,t.initial_prediction_version,d.name AS department,d.code '
        'FROM queue_tokens t JOIN departments d ON d.id=t.department_id WHERE public_key=%s',
        (key,),
    ).fetchone()


# Explicit projections prevent private links, patient IDs, and free-text policy
# references from leaving the versioned staff API.
QUEUE_RECORD_FIELDS = (
    't.id,t.department_id,t.staff_id,t.token_no,t.status,t.priority_class,'
    't.check_in_at,t.called_at,t.service_start_at,t.completed_at,t.ended_at'
)
QUEUE_ORDERS = {
    ('priority', 'asc'): PRIORITY_ORDER + ',t.id',
    (
        'priority',
        'desc',
    ): "CASE t.priority_class WHEN 'expedited' THEN 0 ELSE 1 END DESC,t.check_in_at DESC,t.token_no DESC,t.id DESC",
    ('arrival', 'asc'): 't.check_in_at,t.id',
    ('arrival', 'desc'): 't.check_in_at DESC,t.id DESC',
    ('token', 'asc'): 't.token_no,t.id',
    ('token', 'desc'): 't.token_no DESC,t.id DESC',
}


def staff_queue_page(conn: DatabaseConnection, query):
    where = (
        's.service_date=coalesce(%s::date,(now() AT TIME ZONE d.timezone)::date) '
        'AND (%s::uuid IS NULL OR t.department_id=%s) '
        'AND (%s::uuid IS NULL OR t.staff_id=%s) AND (%s::text IS NULL OR t.status=%s)'
    )
    params = (
        query.day,
        query.department_id,
        query.department_id,
        query.staff_id,
        query.staff_id,
        query.status,
        query.status,
    )
    source = (
        ' FROM queue_tokens t JOIN queue_sessions s ON s.id=t.session_id '
        'JOIN departments d ON d.id=t.department_id WHERE ' + where
    )
    total = conn.execute('SELECT count(*) AS n' + source, params).fetchone()['n']
    rows = conn.execute(
        'SELECT '
        + QUEUE_RECORD_FIELDS
        + source
        + ' ORDER BY '
        + QUEUE_ORDERS[query.sort, query.direction]
        + ' LIMIT %s OFFSET %s',
        (*params, query.page_size, query.offset),
    ).fetchall()
    return rows, total


def staff_queue_record(conn: DatabaseConnection, token_id):
    return conn.execute(
        'SELECT ' + QUEUE_RECORD_FIELDS + ' FROM queue_tokens t WHERE t.id=%s',
        (token_id,),
    ).fetchone()


def staff_queue_history(conn: DatabaseConnection, token_id, limit: int, offset: int):
    # A token has at most one row per event type.
    events = conn.execute(
        'SELECT id,event_type,event_time,staff_id FROM service_events WHERE token_id=%s '
        "ORDER BY event_time, array_position(ARRAY['check_in','called','service_start','completed','cancelled','no_show'], event_type),id",
        (token_id,),
    ).fetchall()
    return events[offset : offset + limit], len(events)

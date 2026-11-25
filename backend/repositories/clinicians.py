"""Persistence shared by clinic management and queue operations."""

from backend.database import DatabaseConnection


def lock_station(conn: DatabaseConnection, staff_id):
    return conn.execute(
        'SELECT * FROM staff WHERE id=%s AND is_active FOR UPDATE',
        (staff_id,),
    ).fetchone()


def schedules_between(conn: DatabaseConnection, start, end):
    return conn.execute(
        'SELECT sc.*,st.display_name FROM staff_schedules sc JOIN staff st ON st.id=sc.staff_id '
        'WHERE service_date BETWEEN %s AND %s ORDER BY start_at LIMIT 500',
        (start, end),
    ).fetchall()


def has_schedule_overlap(conn: DatabaseConnection, staff_id, start, end) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM staff_schedules WHERE staff_id=%s AND status='scheduled' AND start_at<%s AND end_at>%s",
            (staff_id, end, start),
        ).fetchone()
        is not None
    )


def insert_schedule(conn: DatabaseConnection, staff_id, service_date, start, end):
    return conn.execute(
        'INSERT INTO staff_schedules(staff_id,service_date,start_at,end_at) VALUES(%s,%s,%s,%s) RETURNING id',
        (staff_id, service_date, start, end),
    ).fetchone()['id']


def latest_availability_today(conn: DatabaseConnection, staff_id):
    return conn.execute(
        'SELECT status FROM staff_availability WHERE staff_id=%s AND '
        "(changed_at AT TIME ZONE 'Asia/Colombo')::date=(now() AT TIME ZONE 'Asia/Colombo')::date "
        'ORDER BY changed_at DESC LIMIT 1',
        (staff_id,),
    ).fetchone()


DOCTOR_FIELDS = "st.id,st.department_id,st.display_name,st.is_active,coalesce(a.status,'offline') AS availability"
DOCTOR_SOURCE = (
    ' FROM staff st LEFT JOIN LATERAL (SELECT status FROM staff_availability '
    'WHERE staff_id=st.id AND '
    "(changed_at AT TIME ZONE 'Asia/Colombo')::date=(now() AT TIME ZONE 'Asia/Colombo')::date "
    "ORDER BY changed_at DESC LIMIT 1) a ON true WHERE st.staff_type='doctor'"
)


def doctors_page(conn: DatabaseConnection, query):
    where = ' AND (%s::uuid IS NULL OR st.department_id=%s) AND (%s::bool IS NULL OR st.is_active=%s)'
    params = (query.department_id, query.department_id, query.active, query.active)
    order = (
        'st.display_name DESC,st.id DESC'
        if query.direction == 'desc'
        else 'st.display_name,st.id'
    )
    total = conn.execute(
        "SELECT count(*) AS n FROM staff st WHERE st.staff_type='doctor'" + where,
        params,
    ).fetchone()['n']
    rows = conn.execute(
        'SELECT '
        + DOCTOR_FIELDS
        + DOCTOR_SOURCE
        + where
        + ' ORDER BY '
        + order
        + ' LIMIT %s OFFSET %s',
        (*params, query.page_size, query.offset),
    ).fetchall()
    return rows, total


def doctor(conn: DatabaseConnection, doctor_id):
    return conn.execute(
        'SELECT ' + DOCTOR_FIELDS + DOCTOR_SOURCE + ' AND st.id=%s',
        (doctor_id,),
    ).fetchone()


def doctor_schedule(conn: DatabaseConnection, doctor_id, query):
    where = ' WHERE staff_id=%s AND service_date BETWEEN %s AND %s AND (%s::text IS NULL OR status=%s)'
    params = (doctor_id, query.start, query.end, query.status, query.status)
    order = 'start_at DESC,id DESC' if query.direction == 'desc' else 'start_at,id'
    total = conn.execute(
        'SELECT count(*) AS n FROM staff_schedules' + where, params
    ).fetchone()['n']
    rows = conn.execute(
        'SELECT id,staff_id,service_date,start_at,end_at,status FROM staff_schedules'
        + where
        + ' ORDER BY '
        + order
        + ' LIMIT %s OFFSET %s',
        (*params, query.page_size, query.offset),
    ).fetchall()
    return rows, total

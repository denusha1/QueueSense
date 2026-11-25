"""Durable identities are matched only on the clinic-supplied identifier."""

from uuid import UUID

from backend.database import DatabaseConnection


def register(
    conn: DatabaseConnection, external_id: str, actor_id: str
) -> tuple[UUID, bool]:
    while True:
        row = conn.execute(
            'INSERT INTO patients(external_id,created_by) VALUES(%s,%s) '
            'ON CONFLICT (external_id) DO NOTHING RETURNING id',
            (external_id, actor_id),
        ).fetchone()
        if row:
            return row['id'], True
        # At READ COMMITTED this sees the winning insert. If an administrator
        # corrected that identifier between the statements, retry the lookup.
        row = get_by_identifier(conn, external_id)
        if row:
            return row['id'], False


def exists(conn: DatabaseConnection, patient_id: UUID) -> bool:
    return (
        conn.execute('SELECT id FROM patients WHERE id=%s', (patient_id,)).fetchone()
        is not None
    )


def get_by_identifier(conn: DatabaseConnection, external_id: str):
    return conn.execute(
        'SELECT id,external_id FROM patients WHERE external_id=%s', (external_id,)
    ).fetchone()


def get(conn: DatabaseConnection, patient_id: UUID):
    return conn.execute(
        'SELECT id,external_id FROM patients WHERE id=%s', (patient_id,)
    ).fetchone()


def page(
    conn: DatabaseConnection,
    external_id: str | None,
    direction: str,
    limit: int,
    offset: int,
):
    where = ' WHERE external_id=%s' if external_id else ''
    params = (external_id,) if external_id else ()
    order = 'external_id DESC' if direction == 'desc' else 'external_id ASC'
    total = conn.execute(
        'SELECT count(*) AS n FROM patients' + where, params
    ).fetchone()['n']
    rows = conn.execute(
        'SELECT id,external_id FROM patients'
        + where
        + ' ORDER BY '
        + order
        + ' LIMIT %s OFFSET %s',
        (*params, limit, offset),
    ).fetchall()
    return rows, total


def lock(conn: DatabaseConnection, patient_id: UUID):
    return conn.execute(
        'SELECT id,external_id FROM patients WHERE id=%s FOR NO KEY UPDATE',
        (patient_id,),
    ).fetchone()


def update_identifier(conn: DatabaseConnection, patient_id: UUID, external_id: str):
    return conn.execute(
        'UPDATE patients SET external_id=%s WHERE id=%s RETURNING id,external_id',
        (external_id, patient_id),
    ).fetchone()

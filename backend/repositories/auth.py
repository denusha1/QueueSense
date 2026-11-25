"""Persistence for staff login attempts and opaque sessions."""

from backend.database import DatabaseConnection


def active_session(conn: DatabaseConnection, token_hash: str):
    return conn.execute(
        'SELECT u.id::text, u.email, u.role, s.expires_at, s.id AS session_id FROM auth_sessions s '
        'JOIN users u ON u.id=s.user_id '
        "WHERE s.token_hash=%s AND s.auth_mode='opaque' AND s.expires_at > now() AND u.is_active",
        (token_hash,),
    ).fetchone()


def login_attempts(conn: DatabaseConnection, account_hash: str, source_hash: str):
    # Keep counting and recording attempts in the same transaction across workers.
    conn.execute('SELECT pg_advisory_xact_lock(72419022)')
    conn.execute(
        "DELETE FROM login_attempts WHERE attempted_at < now() - interval '1 day'"
    )
    return conn.execute(
        'SELECT count(*) FILTER (WHERE account_hash=%s AND NOT succeeded) AS account, '
        'count(*) FILTER (WHERE source_hash=%s) AS source FROM login_attempts '
        "WHERE attempted_at > now() - interval '15 minutes'",
        (account_hash, source_hash),
    ).fetchone()


def record_attempt(
    conn: DatabaseConnection, account_hash: str, source_hash: str, succeeded: bool
):
    conn.execute(
        'INSERT INTO login_attempts(account_hash,source_hash,succeeded) VALUES(%s,%s,%s)',
        (account_hash, source_hash, succeeded),
    )


def login_account(conn: DatabaseConnection, email: str):
    return conn.execute(
        'SELECT id,email,password_hash,role,is_active FROM users WHERE email=%s',
        (email,),
    ).fetchone()


def enabled_mfa(conn: DatabaseConnection, user_id):
    return conn.execute(
        'SELECT * FROM account_mfa WHERE user_id=%s AND enabled FOR UPDATE',
        (user_id,),
    ).fetchone()


def record_mfa_step(conn: DatabaseConnection, user_id, step: int):
    conn.execute(
        'UPDATE account_mfa SET last_step=%s WHERE user_id=%s', (step, user_id)
    )


def update_password_hash(conn: DatabaseConnection, user_id, password_hash: str):
    conn.execute(
        'UPDATE users SET password_hash=%s WHERE id=%s', (password_hash, user_id)
    )


def delete_session(conn: DatabaseConnection, token_hash: str):
    return conn.execute(
        'DELETE FROM auth_sessions WHERE token_hash=%s RETURNING user_id',
        (token_hash,),
    ).fetchone()


def create_session(
    conn: DatabaseConnection,
    token_hash: str,
    user_id,
    device: str,
    seconds: int,
    mode: str,
):
    conn.execute('DELETE FROM auth_sessions WHERE expires_at <= now()')
    return conn.execute(
        'INSERT INTO auth_sessions(token_hash,user_id,device_label,expires_at,auth_mode) '
        "VALUES(%s,%s,%s,now() + %s * interval '1 second',%s) RETURNING id AS session_id,expires_at",
        (token_hash, user_id, device[:160], seconds, mode),
    ).fetchone()


def rotate_active_session(
    conn: DatabaseConnection, old_hash: str, new_hash: str, mode: str
):
    return conn.execute(
        'UPDATE auth_sessions s SET token_hash=%s FROM users u '
        'WHERE s.token_hash=%s AND s.auth_mode=%s AND s.user_id=u.id AND s.expires_at>now() AND u.is_active '
        'RETURNING u.id::text, u.email, u.role, s.expires_at, s.id AS session_id',
        (new_hash, old_hash, mode),
    ).fetchone()


def active_jwt_session(conn: DatabaseConnection, session_id, user_id):
    return conn.execute(
        'SELECT u.id::text, u.email, u.role, s.expires_at, s.id AS session_id FROM auth_sessions s '
        'JOIN users u ON u.id=s.user_id '
        "WHERE s.id=%s AND u.id=%s AND s.auth_mode='jwt' AND s.expires_at>now() AND u.is_active",
        (session_id, user_id),
    ).fetchone()


def delete_jwt_session(conn: DatabaseConnection, session_id, user_id):
    return conn.execute(
        "DELETE FROM auth_sessions WHERE id=%s AND user_id=%s AND auth_mode='jwt' RETURNING user_id",
        (session_id, user_id),
    ).fetchone()


def delete_refresh_session(conn: DatabaseConnection, token_hash: str):
    return conn.execute(
        "DELETE FROM auth_sessions WHERE token_hash=%s AND auth_mode='jwt' RETURNING user_id",
        (token_hash,),
    ).fetchone()

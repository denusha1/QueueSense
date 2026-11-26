"""Staff authentication and session lifecycle, independent of HTTP cookies."""

import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import NotRequired, TypedDict
from uuid import UUID

from argon2.exceptions import InvalidHashError, VerificationError

from backend.core.config import Settings
from backend.core.errors import ServiceError
from backend.core.jwt import INVALID_TOKEN, issue_access_token, verify_access_token
from backend.core.security import DUMMY_HASH, HASHER, Role, digest
from backend.database import DatabaseConnection, connection
from backend.repositories import auth as repository
from backend.repositories.audit import audit
from backend.security import decrypt, verify_totp


class StaffSession(TypedDict):
    id: str
    email: str
    role: Role
    expires_at: datetime
    session_id: UUID
    access_expires_at: NotRequired[datetime]
    permissions: NotRequired[list[str]]


@dataclass(frozen=True, repr=False)
class SessionTokens:
    access: str
    refresh: str | None = None


def resolve_session(settings: Settings, token: str) -> StaffSession:
    if settings.jwt:
        claims = verify_access_token(settings.jwt, token)
        with connection(settings) as conn:
            user = repository.active_jwt_session(
                conn, claims.session_id, claims.user_id
            )
        if user:
            user['access_expires_at'] = claims.expires_at
    else:
        if not 20 <= len(token) <= 128:
            raise ServiceError(401, 'Please sign in to continue.')
        with connection(settings) as conn:
            user = repository.active_session(conn, digest(token))
    if not user:
        raise ServiceError(401, INVALID_TOKEN)
    return user


def session_tokens(
    settings: Settings, refresh: str, user: StaffSession
) -> SessionTokens:
    if not settings.jwt:
        return SessionTokens(refresh)
    access, expiry = issue_access_token(
        settings.jwt,
        user['id'],
        user['session_id'],
        user['expires_at'],
    )
    user['access_expires_at'] = expiry
    return SessionTokens(access, refresh)


def issue_session(
    conn: DatabaseConnection,
    settings: Settings,
    user,
    old_token: str | None,
    device: str = 'Browser session',
) -> tuple[SessionTokens, StaffSession]:
    secret = secrets.token_urlsafe(32)
    if old_token:
        repository.delete_session(conn, digest(old_token))
    row = repository.create_session(
        conn,
        digest(secret),
        user['id'],
        device,
        settings.jwt.refresh_seconds if settings.jwt else settings.session_seconds,
        'jwt' if settings.jwt else 'opaque',
    )
    session: StaffSession = {
        'id': str(user['id']),
        'email': user['email'],
        'role': user['role'],
        'expires_at': row['expires_at'],
        'session_id': row['session_id'],
    }
    return session_tokens(settings, secret, session), session


def authenticate(
    settings: Settings,
    email: str,
    role: Role,
    peer: str,
    old_token: str | None,
    device: str,
    password: str = '',
    *,
    demo: bool = False,
    otp: str | None = None,
) -> tuple[SessionTokens, StaffSession]:
    account_hash, source_hash = digest(email), digest(peer)
    error = None
    with connection(settings) as conn:
        attempts = repository.login_attempts(conn, account_hash, source_hash)
        if attempts['account'] >= 5 or attempts['source'] >= 60:
            raise ServiceError(
                429,
                'Too many sign-in attempts. Try again in 15 minutes.',
                headers={'Retry-After': '900'},
            )
        user = repository.login_account(conn, email)
        verified = False
        if demo:
            verified = bool(user and email == f'{role}@demo.queuesense.test')
        else:
            try:
                verified = HASHER.verify(
                    user['password_hash'] if user else DUMMY_HASH, password
                )
            except (VerificationError, InvalidHashError):
                pass

        if not verified or not user or not user['is_active']:
            error = ServiceError(
                401, 'Email or password is incorrect, or the account is unavailable.'
            )
        elif user['role'] != role:
            error = ServiceError(
                403, 'This account does not have access to the selected workspace.'
            )
        else:
            mfa = repository.enabled_mfa(conn, user['id'])
            if mfa:
                step = (
                    None
                    if demo
                    else verify_totp(
                        decrypt(mfa['secret_encrypted']), otp, mfa['last_step']
                    )
                )
                if step is None:
                    error = ServiceError(
                        401, 'Authentication code is required or invalid.'
                    )
                else:
                    repository.record_mfa_step(conn, user['id'], step)

        repository.record_attempt(conn, account_hash, source_hash, error is None)
        if error is None:
            if not demo and HASHER.check_needs_rehash(user['password_hash']):
                repository.update_password_hash(conn, user['id'], HASHER.hash(password))
            session = issue_session(conn, settings, user, old_token, device)
            audit(conn, user, 'sign_in', 'user', user['id'], {'demo': demo})
    # Commit failed attempts before returning an authentication error.
    if error:
        raise error
    return session


def valid_refresh_token(token: str | None) -> bool:
    return bool(token and re.fullmatch(r'[A-Za-z0-9_-]{43}', token))


def end_session(
    settings: Settings, access: str | None, refresh: str | None = None
) -> None:
    if not access and not refresh:
        return
    with connection(settings) as conn:
        row = None
        if settings.jwt:
            if valid_refresh_token(refresh):
                row = repository.delete_refresh_session(conn, digest(refresh))
            if not row and access:
                # An authenticated access token also permits revoking its own session.
                try:
                    claims = verify_access_token(settings.jwt, access)
                except ServiceError:
                    pass
                else:
                    row = repository.delete_jwt_session(
                        conn, claims.session_id, claims.user_id
                    )
        elif access and 20 <= len(access) <= 128:
            row = repository.delete_session(conn, digest(access))
        if row:
            audit(conn, {'id': str(row['user_id'])}, 'sign_out', 'user', row['user_id'])


def refresh_session(
    settings: Settings, token: str
) -> tuple[SessionTokens, StaffSession]:
    if settings.jwt:
        if not valid_refresh_token(token):
            raise ServiceError(401, INVALID_TOKEN)
    elif not 20 <= len(token) <= 128:
        raise ServiceError(401, 'Please sign in to continue.')
    replacement = secrets.token_urlsafe(32)
    with connection(settings) as conn:
        user = repository.rotate_active_session(
            conn,
            digest(token),
            digest(replacement),
            'jwt' if settings.jwt else 'opaque',
        )
        if not user:
            raise ServiceError(401, INVALID_TOKEN)
        credentials = session_tokens(settings, replacement, user)
        audit(conn, user, 'refresh_session', 'user', user['id'])
    return credentials, user

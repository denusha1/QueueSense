"""Database-backed authentication; no browser-selected role is trusted for authorization."""
import hashlib
import logging
import os
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

import psycopg
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal['reception', 'doctor', 'manager', 'admin']
COOKIE = 'queuesense_session'
HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))
LOG = logging.getLogger('queuesense.auth')


@dataclass(frozen=True)
class Settings:
    database_url: str
    origins: tuple[str, ...]
    secure_cookie: bool = False
    demo_enabled: bool = False
    session_seconds: int = 8 * 60 * 60

    @classmethod
    def from_env(cls):
        url = os.environ.get('DATABASE_URL', '')
        if not url:
            raise RuntimeError('DATABASE_URL is required')
        production = os.environ.get('APP_ENV') == 'production'
        origins = tuple(x.strip().rstrip('/') for x in os.environ.get('FRONTEND_ORIGINS', 'http://127.0.0.1:3001,http://localhost:3001').split(',') if x.strip())
        demo = os.environ.get('ENABLE_DEMO_LOGIN') == 'true'
        if production and (demo or any(not x.startswith('https://') for x in origins)):
            raise RuntimeError('Production requires HTTPS origins and disabled demo login')
        if not origins:
            raise RuntimeError('At least one frontend origin is required')
        return cls(url, origins, production, demo)


@contextmanager
def connection(settings):
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    role: Role

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if value.count('@') != 1 or any(c.isspace() for c in value):
            raise ValueError('Enter a valid work email')
        return value


class DemoRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Role


WORKSPACES = {
    'reception': {'title': 'Reception workspace', 'description': 'Your place to welcome arrivals and coordinate the queue.', 'capabilities': ['Patient check-in', 'Queue coordination', 'Token status'], 'next': 'Live queue operations are the next planned delivery.'},
    'doctor': {'title': 'Doctor workspace', 'description': 'A focused space for your service queue and availability.', 'capabilities': ['Call next token', 'Record service events', 'Manage availability'], 'next': 'Patient service controls will follow the queue foundation.'},
    'manager': {'title': 'Manager workspace', 'description': 'Understand patient flow and plan clinic capacity.', 'capabilities': ['Operational analytics', 'Bottleneck insights', 'Staffing scenarios'], 'next': 'Live analytics will follow operational data capture.'},
    'admin': {'title': 'Administrator workspace', 'description': 'Manage access and the foundations of your clinic.', 'capabilities': ['User and role management', 'Department configuration', 'Audit history'], 'next': 'Administration controls will arrive in their planned step.'},
}


def create_app(settings=None):
    settings = settings or Settings.from_env()
    app = FastAPI(title='QueueSense API', version='1.0.0')
    app.state.settings = settings

    @app.middleware('http')
    async def headers_and_origin(request, call_next):
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and request.headers.get('origin') not in settings.origins:
            return JSONResponse({'detail': 'Request origin is not allowed.'}, status_code=403, headers={'Cache-Control': 'no-store'})
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.exception_handler(psycopg.Error)
    async def database_error(request, exc):
        LOG.error('database_unavailable path=%s error_type=%s', request.url.path, type(exc).__name__)
        return JSONResponse({'detail': 'The database service is temporarily unavailable. Please try again.'}, status_code=503, headers={'Cache-Control': 'no-store'})

    def current_user(request: Request):
        token = request.cookies.get(COOKIE, '')
        if not 20 <= len(token) <= 128:
            raise HTTPException(401, 'Please sign in to continue.')
        with connection(settings) as conn:
            user = conn.execute('SELECT u.id::text, u.email, u.role, s.expires_at FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=%s AND s.expires_at > now() AND u.is_active', (digest(token),)).fetchone()
        if not user:
            raise HTTPException(401, 'Your session has ended. Please sign in again.')
        return user

    def issue_session(conn, user, response, old_token):
        token = secrets.token_urlsafe(32)
        if old_token:
            conn.execute('DELETE FROM auth_sessions WHERE token_hash=%s', (digest(old_token),))
        conn.execute('DELETE FROM auth_sessions WHERE expires_at <= now()')
        row = conn.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES(%s,%s,now() + %s * interval '1 second') RETURNING expires_at", (digest(token), user['id'], settings.session_seconds)).fetchone()
        response.set_cookie(COOKIE, token, httponly=True, secure=settings.secure_cookie, samesite='lax', max_age=settings.session_seconds, path='/')
        return {'id': str(user['id']), 'email': user['email'], 'role': user['role'], 'expires_at': row['expires_at']}

    def authenticate(email, role, request, response, password=None, demo=False):
        account_hash = digest(email)
        source_hash = digest(request.client.host if request.client else 'unknown')
        error = None
        result = None
        with connection(settings) as conn:
            # A small-clinic login lock makes attempt counting atomic across API workers.
            conn.execute('SELECT pg_advisory_xact_lock(72419022)')
            conn.execute("DELETE FROM login_attempts WHERE attempted_at < now() - interval '1 day'")
            attempts = conn.execute("SELECT count(*) FILTER (WHERE account_hash=%s AND NOT succeeded) AS account, count(*) FILTER (WHERE source_hash=%s) AS source FROM login_attempts WHERE attempted_at > now() - interval '15 minutes'", (account_hash, source_hash)).fetchone()
            if attempts['account'] >= 5 or attempts['source'] >= 60:
                raise HTTPException(429, 'Too many sign-in attempts. Try again in 15 minutes.', headers={'Retry-After': '900'})
            user = conn.execute('SELECT id,email,password_hash,role,is_active FROM users WHERE email=%s', (email,)).fetchone()
            verified = False
            if demo:
                verified = bool(user and email == f'{role}@demo.queuesense.test')
            else:
                try:
                    verified = HASHER.verify(user['password_hash'] if user else DUMMY_HASH, password)
                except (VerificationError, InvalidHashError):
                    pass
            if not verified or not user or not user['is_active']:
                error = HTTPException(401, 'Email or password is incorrect, or the account is unavailable.')
            elif user['role'] != role:
                error = HTTPException(403, 'This account does not have access to the selected workspace.')
            conn.execute('INSERT INTO login_attempts(account_hash,source_hash,succeeded) VALUES(%s,%s,%s)', (account_hash, source_hash, error is None))
            if error is None:
                if not demo and HASHER.check_needs_rehash(user['password_hash']):
                    conn.execute('UPDATE users SET password_hash=%s WHERE id=%s', (HASHER.hash(password), user['id']))
                result = issue_session(conn, user, response, request.cookies.get(COOKIE))
        # Raise outside the transaction so failed-attempt records are committed.
        if error:
            raise error
        return result

    @app.post('/auth/login')
    def login(body: Credentials, request: Request, response: Response):
        return authenticate(body.email, body.role, request, response, body.password)

    @app.get('/auth/demo')
    def demo_status():
        return {'enabled': settings.demo_enabled}

    @app.post('/auth/demo')
    def demo_login(body: DemoRequest, request: Request, response: Response):
        if not settings.demo_enabled:
            raise HTTPException(404, 'Demo sign-in is unavailable.')
        return authenticate(f'{body.role}@demo.queuesense.test', body.role, request, response, demo=True)

    @app.get('/auth/me')
    def me(user=Depends(current_user)):
        return user

    @app.get('/auth/workspace/{role}')
    def workspace(role: Role, user=Depends(current_user)):
        if user['role'] != role:
            raise HTTPException(403, 'You do not have access to this workspace.')
        return {'user': user, 'workspace': WORKSPACES[role]}

    @app.post('/auth/logout')
    def logout(request: Request, response: Response):
        token = request.cookies.get(COOKIE)
        if token:
            with connection(settings) as conn:
                conn.execute('DELETE FROM auth_sessions WHERE token_hash=%s', (digest(token),))
        response.delete_cookie(COOKIE, path='/', secure=settings.secure_cookie, httponly=True, samesite='lax')
        return {'ok': True}

    @app.get('/health')
    def health():
        with connection(settings) as conn:
            conn.execute('SELECT 1 FROM auth_sessions LIMIT 1')
        return {'status': 'ok'}

    from backend.product import attach_product
    attach_product(app, settings, current_user)
    return app

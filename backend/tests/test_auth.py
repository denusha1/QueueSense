import os
import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

from backend.app import COOKIE, HASHER, Settings, create_app, digest

ORIGIN = 'http://127.0.0.1:3001'
PASSWORD = 'QueueSense-Test-Only-2026!'


@pytest.fixture(scope='session')
def test_url():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.fail('Set TEST_DATABASE_URL to a local PostgreSQL database; tests create a unique isolated schema.')
    schema = 'test_auth_' + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    isolated = make_conninfo(url, options=f'-c search_path={schema}')
    try:
        with psycopg.connect(isolated) as conn:
            for migration in sorted(Path('database/migrations').glob('*.sql')):
                conn.execute(migration.read_text())
        yield isolated
    finally:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


@pytest.fixture
def client(test_url):
    with psycopg.connect(test_url) as conn:
        conn.execute('TRUNCATE users, auth_sessions, login_attempts CASCADE')
        password_hash = HASHER.hash(PASSWORD)
        for role in ('reception', 'doctor', 'manager', 'admin'):
            for domain in ('staff.example.test', 'demo.queuesense.test'):
                conn.execute('INSERT INTO users(email,password_hash,role) VALUES(%s,%s,%s)', (f'{role}@{domain}', password_hash, role))
    with TestClient(create_app(Settings(test_url, (ORIGIN,), demo_enabled=True))) as client:
        yield client


def login(client, role='reception', password=PASSWORD, email=None):
    return client.post('/auth/login', json={'email': email or f'{role}@staff.example.test', 'password': password, 'role': role}, headers={'Origin': ORIGIN})


@pytest.mark.parametrize('role', ['reception','doctor','manager','admin'])
def test_real_credentials_and_all_role_boundaries(client, role):
    result = login(client, role)
    assert result.status_code == 200
    assert result.json()['role'] == role
    assert 'password_hash' not in result.json()
    assert client.get('/auth/me').json()['role'] == role
    for requested in ('reception','doctor','manager','admin'):
        assert client.get('/auth/workspace/' + requested).status_code == (200 if requested == role else 403)


def test_cookie_hash_rotation_and_logout(client, test_url):
    result = login(client)
    cookie = result.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=lax' in cookie and 'Max-Age=28800' in cookie
    first = client.cookies[COOKIE]
    with psycopg.connect(test_url) as conn:
        stored = conn.execute('SELECT token_hash FROM auth_sessions').fetchone()[0]
        assert stored == digest(first) and stored != first
    assert login(client).status_code == 200
    assert client.cookies[COOKIE] != first
    with psycopg.connect(test_url) as conn:
        assert conn.execute('SELECT count(*) FROM auth_sessions WHERE token_hash=%s', (digest(first),)).fetchone()[0] == 0
    token = client.cookies[COOKIE]
    assert client.post('/auth/logout', headers={'Origin': ORIGIN}).status_code == 200
    assert COOKIE not in client.cookies
    client.cookies.set(COOKIE, token)
    assert client.get('/auth/me').status_code == 401


def test_wrong_password_unknown_account_and_role_tampering(client):
    wrong = login(client, password='wrong')
    unknown = login(client, email='unknown@staff.example.test')
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    denied = client.post('/auth/login', json={'email': 'reception@staff.example.test', 'password': PASSWORD, 'role': 'admin'}, headers={'Origin': ORIGIN})
    assert denied.status_code == 403 and COOKIE not in client.cookies
    assert client.get('/auth/workspace/admin').status_code == 401


def test_disabled_and_expired_sessions(client, test_url):
    assert login(client).status_code == 200
    with psycopg.connect(test_url) as conn:
        conn.execute("UPDATE auth_sessions SET created_at=now()-interval '2 days', expires_at=now()-interval '1 day'")
    assert client.get('/auth/me').status_code == 401
    assert login(client).status_code == 200
    with psycopg.connect(test_url) as conn:
        conn.execute("UPDATE users SET is_active=false WHERE email='reception@staff.example.test'")
    assert client.get('/auth/me').status_code == 401
    assert login(client).status_code == 401


def test_csrf_and_forged_session(client):
    assert client.post('/auth/demo', json={'role':'admin'}).status_code == 403
    assert client.post('/auth/demo', json={'role':'admin'}, headers={'Origin':'https://evil.example'}).status_code == 403
    assert login(client).status_code == 200
    assert client.post('/auth/logout', headers={'Origin':'https://evil.example'}).status_code == 403
    assert client.get('/auth/me').status_code == 200
    client.cookies.clear()
    client.cookies.set(COOKIE, 'forged-session-token-with-sufficient-length')
    assert client.get('/auth/me').status_code == 401


def test_throttle_survives_new_app_instance(client, test_url):
    for _ in range(5):
        assert login(client, password='wrong').status_code == 401
    with TestClient(create_app(Settings(test_url, (ORIGIN,)))) as second:
        result = login(second)
        assert result.status_code == 429 and result.headers['Retry-After'] == '900'


def test_demo_enabled_and_disabled(client, test_url):
    result = client.post('/auth/demo', json={'role':'manager'}, headers={'Origin':ORIGIN})
    assert result.status_code == 200 and result.json()['role'] == 'manager'
    with TestClient(create_app(Settings(test_url, (ORIGIN,)))) as disabled:
        assert disabled.get('/auth/demo').json()['enabled'] is False
        assert disabled.post('/auth/demo', json={'role':'admin'}, headers={'Origin':ORIGIN}).status_code == 404


def test_validation_email_normalization_and_no_cache(client):
    assert login(client, email='  RECEPTION@staff.example.test ').status_code == 200
    assert client.get('/auth/me').headers['Cache-Control'] == 'no-store'
    result = client.post('/auth/login', headers={'Origin':ORIGIN}, json={'email':'x@y', 'password':'x'*129, 'role':'admin'})
    assert result.status_code == 422


def test_production_cookie_is_secure(client, test_url):
    with TestClient(create_app(Settings(test_url, ('https://clinic.example',), secure_cookie=True)), base_url='https://clinic.example') as secure:
        response = secure.post('/auth/login', json={'email':'admin@staff.example.test','password':PASSWORD,'role':'admin'}, headers={'Origin':'https://clinic.example'})
        assert response.status_code == 200
        assert 'Secure' in response.headers['Set-Cookie']
        assert secure.get('/auth/me').status_code == 200

"""Staff JWT, refresh rotation, and compatibility with the existing role controls."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import jwt
import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app import COOKIE, Settings, create_app
from backend.core.config import JwtSettings
from backend.core.jwt import ACCESS_TYPE, ALGORITHM
from backend.core.security import REFRESH_COOKIE, digest
from backend.tests.test_auth import ORIGIN, PASSWORD, client, login, test_url

ORIGIN_HEADERS = {'Origin': ORIGIN}


@pytest.fixture
def jwt_config():
    return JwtSettings(
        secrets.token_bytes(32), 'queuesense-test', 'queuesense-test-staff'
    )


@pytest.fixture
def staff_api(client, test_url, jwt_config):
    settings = Settings(test_url, (ORIGIN,), automation_enabled=False, jwt=jwt_config)
    with TestClient(create_app(settings)) as api:
        yield api


def api_login(api, role='admin'):
    return api.post(
        '/api/v1/auth/login',
        headers=ORIGIN_HEADERS,
        json={
            'email': f'{role}@staff.example.test',
            'password': PASSWORD,
            'role': role,
        },
    )


def get_with(token, api):
    return api.get('/api/v1/doctors', headers={'Authorization': 'Bearer ' + token})


def assert_unauthorized(response):
    assert response.status_code == 401, response.text
    assert response.json()['error']['code'] == 'unauthenticated'


def test_valid_access_token_and_cookie_storage(staff_api, test_url, jwt_config):
    response = api_login(staff_api)
    assert response.status_code == 200
    body = response.json()
    access = body['access_token']
    refresh = staff_api.cookies[REFRESH_COOKIE]
    assert body['token_type'] == 'Bearer' and staff_api.cookies[COOKIE] == access
    assert refresh not in response.text and 'session_id' not in body['data']
    cookies = response.headers.get_list('set-cookie')
    assert any('HttpOnly' in item and 'SameSite=lax' in item for item in cookies)
    assert any('HttpOnly' in item and 'SameSite=strict' in item for item in cookies)
    claims = jwt.decode(
        access,
        jwt_config.signing_key,
        algorithms=[ALGORITHM],
        issuer=jwt_config.issuer,
        audience=jwt_config.audience,
    )
    assert claims['sub'] == body['data']['id']
    assert claims['exp'] - claims['iat'] == jwt_config.access_seconds
    assert 'email' not in claims and 'role' not in claims
    assert staff_api.get('/auth/me').json()['role'] == 'admin'
    with psycopg.connect(test_url) as conn:
        row = conn.execute(
            'SELECT token_hash,auth_mode FROM auth_sessions WHERE id=%s',
            (claims['sid'],),
        ).fetchone()
    assert row == (digest(refresh), 'jwt')
    staff_api.cookies.clear()
    assert get_with(access, staff_api).status_code == 200
    assert_unauthorized(get_with(refresh, staff_api))


@pytest.mark.parametrize(
    'variant',
    [
        'expired',
        'signature',
        'malformed',
        'issuer',
        'audience',
        'type',
        'algorithm',
        'missing_claim',
    ],
)
def test_reject_invalid_jwt_variants(staff_api, jwt_config, variant):
    response = api_login(staff_api)
    good = response.json()['access_token']
    claims = jwt.decode(
        good,
        jwt_config.signing_key,
        algorithms=[ALGORITHM],
        issuer=jwt_config.issuer,
        audience=jwt_config.audience,
    )
    key, algorithm = jwt_config.signing_key, ALGORITHM
    if variant == 'expired':
        past = int(datetime.now(timezone.utc).timestamp()) - 100
        claims.update(iat=past, nbf=past, exp=past + 60)
    elif variant == 'signature':
        key = secrets.token_bytes(32)
    elif variant == 'issuer':
        claims['iss'] = 'different-issuer'
    elif variant == 'audience':
        claims['aud'] = 'different-audience'
    elif variant == 'type':
        claims['token_use'] = 'refresh'
    elif variant == 'algorithm':
        key, algorithm = secrets.token_bytes(48), 'HS384'
    elif variant == 'missing_claim':
        del claims['sid']

    invalid = (
        'this.is.malformed'
        if variant == 'malformed'
        else jwt.encode(
            claims,
            key,
            algorithm=algorithm,
            headers={'typ': ACCESS_TYPE},
        )
    )
    result = get_with(invalid, staff_api)
    assert_unauthorized(result)
    assert result.headers['WWW-Authenticate'] == 'Bearer'
    assert invalid not in result.text


def test_missing_token_and_old_opaque_cookie_are_denied(client, staff_api):
    assert_unauthorized(staff_api.get('/api/v1/doctors'))
    assert_unauthorized(staff_api.get('/auth/me'))
    assert login(client, 'admin').status_code == 200
    opaque_token = client.cookies[COOKIE]
    staff_api.cookies.set(COOKIE, opaque_token)
    assert_unauthorized(staff_api.get('/auth/me'))
    assert_unauthorized(staff_api.post('/auth/refresh', headers=ORIGIN_HEADERS))


def test_refresh_rotation_is_single_use_and_logout_revokes_all_access(
    staff_api, test_url, jwt_config
):
    issued = api_login(staff_api).json()
    old_access = issued['access_token']
    old_refresh = staff_api.cookies[REFRESH_COOKIE]
    barrier = Barrier(2)

    def refresh(_):
        app = create_app(
            Settings(test_url, (ORIGIN,), automation_enabled=False, jwt=jwt_config)
        )
        with TestClient(app) as peer:
            peer.cookies.set(REFRESH_COOKIE, old_refresh)
            barrier.wait(timeout=10)
            result = peer.post('/api/v1/auth/refresh', headers=ORIGIN_HEADERS)
            return result, result.cookies.get(REFRESH_COOKIE)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(refresh, range(2)))
    assert sorted(response.status_code for response, _ in results) == [200, 401]
    refreshed, current_refresh = next(
        (r, token) for r, token in results if r.status_code == 200
    )
    current_access = refreshed.json()['access_token']
    assert current_refresh != old_refresh and current_access != old_access
    assert refreshed.json()['data']['expires_at'] == issued['data']['expires_at']

    denied = staff_api.post('/api/v1/auth/refresh', headers=ORIGIN_HEADERS)
    assert_unauthorized(denied)  # This client still has the consumed refresh cookie.
    staff_api.cookies.clear()
    staff_api.cookies.set(REFRESH_COOKIE, current_refresh)
    signed_out = staff_api.post('/api/v1/auth/logout', headers=ORIGIN_HEADERS)
    assert signed_out.status_code == 204
    assert len(signed_out.headers.get_list('set-cookie')) == 2
    assert_unauthorized(get_with(old_access, staff_api))
    assert_unauthorized(get_with(current_access, staff_api))
    staff_api.cookies.clear()
    staff_api.cookies.set(REFRESH_COOKIE, current_refresh)
    assert_unauthorized(staff_api.post('/api/v1/auth/refresh', headers=ORIGIN_HEADERS))


def test_expired_refresh_and_disabled_account_cannot_reauthenticate(
    staff_api, test_url
):
    issued = api_login(staff_api, 'doctor').json()
    with psycopg.connect(test_url) as conn:
        conn.execute(
            "UPDATE auth_sessions SET created_at=now()-interval '2 hours', expires_at=now()-interval '1 hour'"
        )
    assert_unauthorized(staff_api.post('/auth/refresh', headers=ORIGIN_HEADERS))
    assert_unauthorized(get_with(issued['access_token'], staff_api))
    second = api_login(staff_api, 'doctor').json()
    with psycopg.connect(test_url) as conn:
        conn.execute("UPDATE users SET is_active=false WHERE role='doctor'")
    assert_unauthorized(get_with(second['access_token'], staff_api))
    assert_unauthorized(staff_api.post('/auth/refresh', headers=ORIGIN_HEADERS))


def test_production_requires_key_and_hides_public_schema(
    monkeypatch, client, test_url, jwt_config
):
    monkeypatch.setenv('DATABASE_URL', 'unused')
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('FRONTEND_ORIGINS', 'https://clinic.example.test')
    monkeypatch.delenv('JWT_SIGNING_SECRET', raising=False)
    with pytest.raises(RuntimeError, match='JWT_SIGNING_SECRET'):
        Settings.from_env()
    settings = Settings(
        test_url,
        ('https://clinic.example.test',),
        secure_cookie=True,
        automation_enabled=False,
        jwt=jwt_config,
    )
    with TestClient(
        create_app(settings), base_url='https://clinic.example.test'
    ) as api:
        assert api.get('/health').status_code == 200
        assert api.get('/docs').status_code == 404
        assert api.get('/openapi.json').status_code == 404
        assert_unauthorized(api.get('/health/services'))
        issued = api.post(
            '/auth/login',
            headers={'Origin': 'https://clinic.example.test'},
            json={
                'email': 'admin@staff.example.test',
                'role': 'admin',
                'password': PASSWORD,
            },
        )
        assert issued.status_code == 200
        cookies = issued.headers.get_list('set-cookie')
        assert len(cookies) == 2 and all(
            'Secure' in cookie and 'HttpOnly' in cookie for cookie in cookies
        )

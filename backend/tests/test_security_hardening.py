"""Regression tests for the API security and outbound transport controls."""

import secrets
from concurrent.futures import ThreadPoolExecutor

import jwt
import pytest
import requests
from fastapi.testclient import TestClient

from backend.app import Settings, create_app
from backend.core import rate_limit
from backend.core.config import JwtSettings, frontend_origin
from backend.core.errors import ServiceError
from backend.core.jwt import ACCESS_TYPE, ALGORITHM
from backend.delivery import PushSession, validate_push_endpoint
from backend.core.config import DeliverySettings
from backend.tests.test_api_v1 import assert_error
from backend.tests.test_auth import ORIGIN, client, login, test_url  # noqa: F401
from backend.tests.test_jwt_auth import api_login
from backend.tests.test_product import clinic, post  # noqa: F401


@pytest.fixture
def api():
    app = create_app(
        Settings('unused', (ORIGIN,), secure_cookie=True, automation_enabled=False)
    )
    with TestClient(app) as browser:
        yield browser


@pytest.mark.parametrize(
    'origins',
    [
        [],
        ['null'],
        ['https://outside.example.test'],
        [ORIGIN, ORIGIN],
        [ORIGIN, 'https://outside.example.test'],
        [ORIGIN + ', https://outside.example.test'],
    ],
)
def test_mutation_requires_one_trusted_origin(api, origins):
    result = api.post(
        '/api/v1/auth/logout', headers=[('Origin', value) for value in origins]
    )
    assert_error(result, 403, 'forbidden')
    assert 'Access-Control-Allow-Origin' not in result.headers


def test_api_fails_closed_for_cross_origin_preflights_and_uses_security_headers(api):
    response = api.options(
        '/api/v1/queue',
        headers={
            'Origin': 'https://outside.example.test',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'authorization,content-type',
        },
    )
    assert response.status_code == 405
    assert 'Access-Control-Allow-Origin' not in response.headers
    assert 'Access-Control-Allow-Credentials' not in response.headers
    assert response.headers['Cross-Origin-Resource-Policy'] == 'same-origin'
    assert response.headers['Strict-Transport-Security'] == 'max-age=31536000'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['Referrer-Policy'] == 'no-referrer'
    assert "default-src 'none'" in response.headers['Content-Security-Policy']
    assert_error(api.get('/api/v1/queue'), 401, 'unauthenticated')
    assert (
        api.post('/api/v1/auth/logout', headers={'Origin': ORIGIN}).status_code == 204
    )


@pytest.mark.parametrize(
    'origin',
    [
        '*',
        'https://*.example.test',
        'https://clinic.test/patient',
        'https://clinic.test?query=secret',
        'https://clinic.test#',
        'https://staff@clinic.test',
        'https://clinic.test:0',
        'https://clinic.test:',
        'https://clinic.test:70000',
        'https://clinic.test\\wrong',
        'https:// bad.test',
    ],
)
def test_reject_invalid_origin_configuration(origin):
    with pytest.raises(RuntimeError, match='FRONTEND_ORIGINS'):
        frontend_origin(origin)


def test_origin_configuration_normalizes_browser_serialization():
    assert (
        frontend_origin('https://Clinic.Example.test:443/')
        == 'https://clinic.example.test'
    )
    assert frontend_origin('http://[::1]:3001') == 'http://[::1]:3001'


def test_jwt_ignores_request_roles_and_rejects_unsupported_headers(client, test_url):
    config = JwtSettings(secrets.token_bytes(32), 'test-issuer', 'test-audience')
    settings = Settings(test_url, (ORIGIN,), automation_enabled=False, jwt=config)
    with TestClient(create_app(settings)) as api:
        response = api_login(api, 'manager')
        assert response.status_code == 200, response.text
        token = response.json()['access_token']
        claims = jwt.decode(
            token,
            config.signing_key,
            algorithms=[ALGORITHM],
            issuer=config.issuer,
            audience=config.audience,
        )
        claims.update(role='admin', permissions=['queue:read', 'users:manage'])
        api.cookies.clear()
        headers = {'typ': ACCESS_TYPE}
        internally_signed = jwt.encode(
            claims, config.signing_key, algorithm=ALGORITHM, headers=headers
        )
        assert_error(
            api.get(
                '/api/v1/queue',
                headers={
                    'Authorization': 'Bearer ' + internally_signed,
                    'X-Role': 'admin',
                },
            ),
            403,
            'forbidden',
        )
        wrong_profile = jwt.encode(
            claims,
            config.signing_key,
            algorithm=ALGORITHM,
            headers={**headers, 'kid': 'unexpected-key-label'},
        )
        response = api.get(
            '/api/v1/doctors', headers={'Authorization': 'Bearer ' + wrong_profile}
        )
        assert_error(response, 401, 'unauthenticated')
        assert wrong_profile not in response.text


def test_sql_search_treats_punctuation_as_data_and_rejects_control_characters(
    client, clinic
):
    dep, _ = clinic
    token = post(client, '/queue/check-in', {'department_id': dep['id']})
    assert token.status_code == 201
    filtered = client.get('/queue/page', params={'search': "O'Neil_%<b>sample</b>"})
    assert filtered.status_code == 200 and filtered.json()['total'] == 0
    assert client.get('/queue/page').json()['total'] == 1
    rejected = post(
        client,
        '/queue/check-in',
        {
            'department_id': dep['id'],
            'priority_reason': 'private\x00reason',
        },
    )
    assert_error(rejected, 422, 'validation_error')
    assert 'private' not in rejected.text


def test_public_status_rate_limit_sets_retry_after_and_recovers(api, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(rate_limit, 'monotonic', lambda: clock[0])
    api.app.state.public_status_limiter = rate_limit.SlidingWindowLimiter(
        limit=2, window_seconds=60
    )
    path = '/patient/invalid-key'
    assert api.get(path).status_code == 404
    assert api.get(path).status_code == 404
    clock[0] += 10
    response = api.get(path)
    assert_error(response, 429, 'rate_limited')
    assert response.headers['Retry-After'] == '50'
    clock[0] += 50
    assert api.get(path).status_code == 404


def test_public_rate_limiter_caps_concurrent_calls():
    limiter = rate_limit.SlidingWindowLimiter(limit=4, window_seconds=60)

    def check(_):
        try:
            limiter.check()
        except ServiceError as exc:
            return exc.status_code
        return 200

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(check, range(16)))
    assert responses.count(200) == 4
    assert responses.count(429) == 12


def test_push_transport_enforces_https_hosts_and_disables_redirects(monkeypatch):
    monkeypatch.delenv('PUSH_ALLOWED_HOSTS', raising=False)
    captured = {}

    def request(_session, method, url, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(requests.Session, 'request', request)
    config = DeliverySettings.from_env()
    safe = 'https://fcm.googleapis.com/sample'
    validate_push_endpoint(safe, config)
    for invalid in (
        'http://fcm.googleapis.com/sample',
        'https://fcm.googleapis.com:400/sample',
        'https://elsewhere.example.test/sample',
        'https://@fcm.googleapis.com/sample',
    ):
        with pytest.raises(ServiceError):
            validate_push_endpoint(invalid, config)
    with PushSession() as session:
        session.post(safe, allow_redirects=True)
    assert captured['allow_redirects'] is False

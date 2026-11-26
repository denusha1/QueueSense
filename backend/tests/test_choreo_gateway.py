"""Origin contract coverage with synthetic Choreo signing keys."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from backend.app import Settings, create_app
from backend.core.choreo import ASSERTION_HEADER, CONTEXT_CLAIM, ChoreoSettings
from backend.core.config import CLINIC_TIMEZONE
from backend.tests.test_auth import ORIGIN, client, test_url  # noqa: F401
from backend.tests.test_product import clinic  # noqa: F401

PATH = '/api/integrations/v1/wait-time-summary'
ISSUER = 'wso2.org/products/am'
AUDIENCE = 'queuesense-pilot-development'
CONTEXT = '/test-org/test-project/queuesense-weekly-wait/v1.0'
JWK_URL = 'https://gateway.example.invalid/.wellknown/jwks'
KID = 'test-gateway-key'


@pytest.fixture(scope='module')
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def assertion(key, **claims):
    now = int(datetime.now(timezone.utc).timestamp())
    return jwt.encode(
        {
            'iss': ISSUER,
            'aud': [AUDIENCE],
            'iat': now,
            'exp': now + 60,
            'jti': str(uuid4()),
            CONTEXT_CLAIM: CONTEXT,
            **claims,
        },
        key,
        algorithm='RS256',
        headers={'kid': KID},
    )


def app_for(database, department, key, monkeypatch):
    settings = Settings(
        database,
        (ORIGIN,),
        automation_enabled=False,
        choreo=ChoreoSettings(JWK_URL, ISSUER, AUDIENCE, CONTEXT, department),
    )
    app = create_app(settings)
    jwk = jwt.PyJWK.from_json(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    monkeypatch.setattr(
        app.state.choreo_verifier.keys, 'get_signing_key', lambda kid: jwk
    )
    return app


def last_monday():
    today = datetime.now(CLINIC_TIMEZONE).date()
    return today - timedelta(days=today.weekday() + 7)


def test_route_is_disabled_by_default():
    with TestClient(
        create_app(Settings('unused', (ORIGIN,), automation_enabled=False))
    ) as api:
        response = api.get(PATH)
    assert response.status_code == 404


def test_environment_fails_on_partial_or_untrusted_jwks(monkeypatch):
    env = {
        'CHOREO_JWKS_URL': JWK_URL,
        'CHOREO_ASSERTION_ISSUER': ISSUER,
        'CHOREO_ASSERTION_AUDIENCE': AUDIENCE,
        'CHOREO_ASSERTION_CONTEXT': CONTEXT,
        'CHOREO_DEPARTMENT_ID': str(uuid4()),
    }
    for name in env:
        monkeypatch.delenv(name, raising=False)
    assert ChoreoSettings.from_env() is None
    monkeypatch.setenv('CHOREO_JWKS_URL', JWK_URL)
    with pytest.raises(RuntimeError):
        ChoreoSettings.from_env()
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert ChoreoSettings.from_env().api_context == CONTEXT
    monkeypatch.setenv(
        'CHOREO_JWKS_URL', 'http://gateway.example.invalid/.wellknown/jwks'
    )
    with pytest.raises(RuntimeError):
        ChoreoSettings.from_env()


def test_gateway_rejects_invalid_credentials_and_limits_scope(rsa_key, monkeypatch):
    dept = uuid4()
    app = app_for('unused', dept, rsa_key, monkeypatch)
    params = {'department_id': str(dept), 'week_start': str(last_monday())}
    good = assertion(rsa_key)
    expired = int(datetime.now(timezone.utc).timestamp()) - 1
    another_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with TestClient(app) as api:
        cases = [
            ({}, 401),
            ({'Authorization': 'Bearer ' + good}, 401),
            ([(ASSERTION_HEADER, good), (ASSERTION_HEADER, good)], 401),
            ({ASSERTION_HEADER: assertion(another_key)}, 401),
            ({ASSERTION_HEADER: assertion(rsa_key, aud='wrong')}, 401),
            ({ASSERTION_HEADER: assertion(rsa_key, aud=None)}, 401),
            ({ASSERTION_HEADER: assertion(rsa_key, iss='wrong')}, 401),
            ({ASSERTION_HEADER: assertion(rsa_key, exp=expired)}, 401),
            ({ASSERTION_HEADER: assertion(rsa_key, **{CONTEXT_CLAIM: '/wrong'})}, 403),
        ]
        for headers, expected in cases:
            result = api.get(PATH, params=params, headers=headers)
            assert result.status_code == expected, result.text
            assert set(result.json()) == {'success', 'error', 'request_id'}
            assert good not in result.text
        headers = {ASSERTION_HEADER: good}
        assert (
            api.get(
                PATH, params={**params, 'department_id': str(uuid4())}, headers=headers
            ).status_code
            == 403
        )
        assert (
            api.get(
                PATH, params={**params, 'staff_id': str(uuid4())}, headers=headers
            ).status_code
            == 422
        )
        assert (
            api.get(
                PATH,
                params={**params, 'week_start': last_monday() + timedelta(days=1)},
                headers=headers,
            ).status_code
            == 422
        )
        assert (
            api.get(
                PATH,
                params={**params, 'week_start': last_monday() + timedelta(days=7)},
                headers=headers,
            ).status_code
            == 422
        )
        assert api.get('/api/v1/patients', headers=headers).status_code == 401

        def offline(_kid):
            raise jwt.PyJWKClientConnectionError('private networking details')

        monkeypatch.setattr(app.state.choreo_verifier.keys, 'get_signing_key', offline)
        failure = api.get(PATH, params=params, headers=headers)
        assert failure.status_code == 503 and 'private networking' not in failure.text


def test_gateway_suppresses_small_cohorts_and_returns_only_department_aggregates(
    clinic, test_url, rsa_key, monkeypatch
):
    department, doctor = clinic
    dept = UUID(department['id'])
    app = app_for(test_url, dept, rsa_key, monkeypatch)
    week = last_monday()
    check_in = datetime.combine(week, datetime.min.time(), CLINIC_TIMEZONE)
    params = {'department_id': str(dept), 'week_start': week}
    headers = {ASSERTION_HEADER: assertion(rsa_key)}
    with TestClient(app) as api:
        hidden = api.get(PATH, params=params, headers=headers)
        assert hidden.status_code == 200, hidden.text
        assert hidden.json()['data'] == {
            'department_id': str(dept),
            'week_start': str(week),
            'suppressed': True,
            'metrics': None,
        }
        with psycopg.connect(test_url) as conn:
            session = conn.execute(
                'INSERT INTO queue_sessions(department_id,service_date,opened_at,closed_at) '
                'VALUES(%s,%s,%s,%s) RETURNING id',
                (dept, week, check_in, check_in + timedelta(hours=23)),
            ).fetchone()[0]
            for number in range(1, 11):
                arrival = check_in + timedelta(minutes=number * 15)
                completed = arrival + timedelta(minutes=11)
                conn.execute(
                    'INSERT INTO queue_tokens(session_id,department_id,staff_id,token_no,synthetic_patient_id,status,'
                    'check_in_at,called_at,service_start_at,completed_at,ended_at) '
                    "VALUES(%s,%s,%s,%s,'SYN-GATEWAY','completed',%s,%s,%s,%s,%s)",
                    (
                        session,
                        dept,
                        doctor['id'],
                        number,
                        arrival,
                        arrival + timedelta(minutes=1),
                        arrival + timedelta(minutes=5),
                        completed,
                        completed,
                    ),
                )
        ready = api.get(PATH, params=params, headers=headers)
        assert ready.status_code == 200, ready.text
        assert ready.headers['cache-control'] == 'no-store'
        assert ready.json()['data']['metrics'] == {
            'measured_waits': 10,
            'average_wait': 5,
            'median_wait': 5,
            'p90_wait': 5,
        }
        assert 'SYN-GATEWAY' not in ready.text

"""Safe errors, correlation, and transaction rollback through the HTTP boundary."""

import json
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.api.traffic import limit_public_link
from backend.app import COOKIE, Settings, create_app
from backend.core.config import CLINIC_TIMEZONE
from backend.repositories.queue import lock_queue_writes
from backend.services import importer, queue
from backend.tests.test_auth import ORIGIN, client, login, test_url
from backend.tests.test_product import clinic

ORIGIN_HEADERS = {'Origin': ORIGIN}


def check_error(response, status, code, *, legacy=False):
    assert response.status_code == status, response.text
    payload = response.json()
    assert payload['success'] is False
    assert payload['error']['code'] == code
    assert payload['error']['message']
    assert 'detail' in payload if legacy else 'detail' not in payload
    assert UUID(payload['request_id']).version == 4
    assert response.headers['X-Request-ID'] == payload['request_id']
    assert response.headers['Cache-Control'] == 'no-store'
    return payload


@pytest.fixture
def dry_api():
    app = create_app(Settings('unused', (ORIGIN,), automation_enabled=False))
    app.dependency_overrides[limit_public_link] = lambda: None
    with TestClient(app) as api:
        yield api


@pytest.mark.parametrize('prefix', ['', '/api/v1'])
def test_malformed_json_is_400_and_does_not_echo_body(dry_api, prefix):
    request_id = str(uuid4())
    response = dry_api.post(
        prefix + '/auth/login',
        content='{"password":"sensitive-password" "role":"doctor"}',
        headers={
            **ORIGIN_HEADERS,
            'Content-Type': 'application/json',
            'X-Request-ID': request_id,
        },
    )
    payload = check_error(response, 400, 'bad_request', legacy=not prefix)
    assert payload['request_id'] == request_id
    assert 'sensitive-password' not in response.text


@pytest.mark.parametrize('prefix', ['', '/api/v1'])
def test_validation_never_echoes_values_or_unknown_field_names(dry_api, prefix):
    response = dry_api.post(
        prefix + '/auth/login',
        headers=ORIGIN_HEADERS,
        json={
            'email': 'private\x00email@example.test',
            'role': 'doctor',
            'password': 'secret' * 30,
            'private-token-field': 'private-token-value',
        },
    )
    payload = check_error(response, 422, 'validation_error', legacy=not prefix)
    assert {issue['field'] for issue in payload['error']['details']} == {
        'body',
        'body.email',
        'body.password',
    }
    for private in (
        'private-token-field',
        'private-token-value',
        'secret',
        'example.test',
    ):
        assert private not in response.text


def test_correlation_and_origin_rejection(dry_api):
    unknown = dry_api.get('/missing', headers={'X-Request-ID': 'private-token'})
    first = check_error(unknown, 404, 'not_found', legacy=True)['request_id']
    assert 'private-token' not in unknown.text
    duplicate = str(uuid4())
    denied = dry_api.post(
        '/api/v1/auth/logout',
        headers=[('X-Request-ID', duplicate), ('X-Request-ID', duplicate)],
    )
    second = check_error(denied, 403, 'forbidden')['request_id']
    assert first != second and second != duplicate
    demo = dry_api.get('/auth/demo', headers={'X-Request-ID': duplicate})
    assert demo.status_code == 200 and demo.headers['X-Request-ID'] == duplicate
    unauthenticated = dry_api.get('/api/v1/queue')
    check_error(unauthenticated, 401, 'unauthenticated')


def test_bad_capability_key_is_rejected_before_database_access(dry_api):
    request = dry_api.get('/patient/' + 'x' * 35 + '$')
    check_error(request, 404, 'not_found', legacy=True)


def test_expected_conflict_and_rate_limit_use_shared_envelope(client, clinic, test_url):
    department, _ = clinic
    token = client.post(
        '/api/v1/queue',
        json={'department_id': department['id']},
        headers=ORIGIN_HEADERS,
    ).json()['data']
    result = client.patch(
        '/api/v1/queue/' + token['id'],
        json={'status': 'completed'},
        headers=ORIGIN_HEADERS,
    )
    check_error(result, 409, 'conflict')
    from backend.core.security import digest

    email = 'reception@staff.example.test'
    with psycopg.connect(test_url) as conn:
        conn.execute(
            'INSERT INTO login_attempts(account_hash,source_hash,succeeded) '
            "SELECT %s,'synthetic-peer',false FROM generate_series(1,5)",
            (digest(email),),
        )
    limited = client.post(
        '/api/v1/auth/login',
        json={'email': email, 'role': 'reception', 'password': 'synthetic'},
        headers=ORIGIN_HEADERS,
    )
    check_error(limited, 429, 'rate_limited')
    assert limited.headers['Retry-After'] == '900'


def test_database_statement_timeout_rolls_back_token_events_and_audit(
    client,
    clinic,
    test_url,
    monkeypatch,
    caplog,
):
    department, _ = clinic
    original = queue.repository.record_event

    def slow_event(conn, *args):
        original(conn, *args)
        conn.execute('SELECT pg_sleep(0.4)')

    monkeypatch.setattr(queue.repository, 'record_event', slow_event)
    app = create_app(
        Settings(
            test_url,
            (ORIGIN,),
            automation_enabled=False,
            db_statement_timeout_ms=100,
        )
    )
    with TestClient(app) as api:
        api.cookies.set(COOKIE, client.cookies[COOKIE])
        response = api.post(
            '/queue/check-in',
            json={'department_id': department['id']},
            headers=ORIGIN_HEADERS,
        )
    payload = check_error(response, 504, 'timeout', legacy=True)
    assert 'pg_sleep' not in response.text and 'pg_sleep' not in caplog.text
    logs = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == 'queuesense.api'
    ]
    assert logs[-1]['request_id'] == payload['request_id']
    assert logs[-1]['route'] == '/queue/check-in'
    with psycopg.connect(test_url) as conn:
        counts = conn.execute(
            'SELECT (SELECT count(*) FROM queue_tokens),(SELECT count(*) FROM service_events),'
            "(SELECT count(*) FROM notifications),(SELECT count(*) FROM audit_logs WHERE action='check_in')"
        ).fetchone()
    assert counts == (0, 0, 0, 0)


def test_database_lock_limit_returns_retryable_error(client, clinic, test_url):
    department, _ = clinic
    app = create_app(
        Settings(
            test_url,
            (ORIGIN,),
            automation_enabled=False,
            db_lock_timeout_ms=60,
        )
    )
    with psycopg.connect(test_url) as locked, TestClient(app) as api:
        lock_queue_writes(locked)
        api.cookies.set(COOKIE, client.cookies[COOKIE])
        response = api.post(
            '/queue/check-in',
            json={'department_id': department['id']},
            headers=ORIGIN_HEADERS,
        )
        check_error(response, 504, 'timeout', legacy=True)
    assert client.get('/queue/live').json()['tokens'] == []


def test_import_rejects_bad_values_safely_and_aborts_on_database_failure(
    client,
    clinic,
    test_url,
    monkeypatch,
):
    day = (datetime.now(CLINIC_TIMEZONE) - timedelta(days=4)).date()
    example = f'completed,{day}T08:00:00+05:30,{day}T08:01:00+05:30,{day}T08:02:00+05:30,{day}T08:10:00+05:30,{day}T08:10:00+05:30'
    headings = 'department,token_no,status,check_in_at,called_at,service_start_at,completed_at,ended_at'
    invalid = client.post(
        '/data/import',
        headers=ORIGIN_HEADERS,
        json={
            'csv_text': f'{headings}\nTEST,sensitive-cell,{example}',
            'dry_run': True,
        },
    )
    assert invalid.status_code == 200
    assert invalid.json()['errors'] == [
        {'row': 2, 'message': 'Token number must be an integer.'}
    ]
    assert 'sensitive-cell' not in invalid.text
    original = importer.import_row

    def fail_second(conn, row, *args):
        if row['token_no'] == '2':
            raise psycopg.errors.QueryCanceled('private SQL statement')
        return original(conn, row, *args)

    monkeypatch.setattr(importer, 'import_row', fail_second)
    result = client.post(
        '/data/import',
        headers=ORIGIN_HEADERS,
        json={
            'csv_text': f'{headings}\nTEST,1,{example}\nTEST,2,{example}',
            'dry_run': False,
        },
    )
    check_error(result, 504, 'timeout', legacy=True)
    assert 'private SQL statement' not in result.text
    with psycopg.connect(test_url) as conn:
        assert conn.execute('SELECT count(*) FROM queue_tokens').fetchone()[0] == 0


def test_public_patient_response_drops_extra_fields(dry_api, monkeypatch):
    monkeypatch.setattr(
        queue,
        'patient',
        lambda *_args: {
            'token': 'TEST-001',
            'department': 'Test',
            'status': 'waiting',
            'priority_class': 'standard',
            'position': 1,
            'patients_ahead': 0,
            'estimated_wait': None,
            'prediction_source': None,
            'explanation': None,
            'initial_prediction': None,
            'actual_wait': None,
            'prediction_error': None,
            'notice': 'Please wait.',
            'public_key': 'private-tracking-key',
            'patient_id': 'private-id',
        },
    )
    result = dry_api.get('/patient/' + 'a' * 35)
    assert result.status_code == 200
    assert 'public_key' not in result.json() and 'patient_id' not in result.json()


def test_nested_validation_keys_cannot_appear_in_errors(dry_api):
    result = dry_api.post(
        '/patient/' + 'a' * 35 + '/delivery/push',
        headers=ORIGIN_HEADERS,
        json={
            'endpoint': 'https://example.test/push',
            'consent': True,
            'keys': {'private-dynamic-key': []},
        },
    )
    error = check_error(result, 422, 'validation_error', legacy=True)
    assert 'private-dynamic-key' not in result.text
    assert error['error']['details'][0]['field'] == 'body.keys'


def test_unexpected_legacy_failure_is_safe_and_correlated(dry_api, monkeypatch, caplog):
    def fail(*_args):
        raise RuntimeError('Internal SQL and a private patient key')

    monkeypatch.setattr(queue, 'patient', fail)
    result = dry_api.get('/patient/' + 'a' * 35)
    error = check_error(result, 500, 'internal_error', legacy=True)
    assert 'Internal SQL' not in result.text
    assert 'Internal SQL' not in caplog.text
    assert error['request_id'] in caplog.text

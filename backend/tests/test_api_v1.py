"""Contract and PostgreSQL integration tests for the private v1 staff API."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.api.v1.dependencies import current_staff
from backend.app import COOKIE, Settings, create_app
from backend.core.config import CLINIC_TIMEZONE
from backend.services import queue
from backend.tests.test_auth import ORIGIN, PASSWORD, client, login, test_url
from backend.tests.test_product import clinic

V1 = '/api/v1'
ORIGIN_HEADERS = {'Origin': ORIGIN}
V1_OPERATIONS = {
    '/auth/login': {'post'},
    '/auth/refresh': {'post'},
    '/auth/logout': {'post'},
    '/patients': {'get', 'post'},
    '/patients/{patient_id}': {'get', 'patch'},
    '/queue': {'get', 'post'},
    '/queue/{token_id}': {'get', 'patch'},
    '/queue/{token_id}/history': {'get'},
    '/doctors': {'get'},
    '/doctors/{doctor_id}': {'get'},
    '/doctors/{doctor_id}/schedule': {'get'},
    '/analytics/waiting-time': {'get'},
    '/analytics/peak-hours': {'get'},
    '/analytics/queue-performance': {'get'},
}


def create(client, path, body=None):
    return client.post(V1 + path, json=body, headers=ORIGIN_HEADERS)


def update(client, path, body):
    return client.patch(V1 + path, json=body, headers=ORIGIN_HEADERS)


def assert_error(result, status, code):
    assert result.status_code == status, result.text
    assert result.json()['error']['code'] == code
    assert 'message' in result.json()['error']
    assert result.headers.get('Cache-Control') == 'no-store'


def test_v1_contract_is_documented_with_cookie_and_response_models():
    spec = create_app(Settings('unused', (ORIGIN,), automation_enabled=False)).openapi()
    paths = {
        p[len(V1) :]: set(methods)
        for p, methods in spec['paths'].items()
        if p.startswith(V1 + '/')
    }
    assert paths == V1_OPERATIONS
    scheme = spec['components']['securitySchemes']['QueueSenseStaffSession']
    assert scheme['in'] == 'cookie' and scheme['name'] == COOKIE
    queue = spec['paths'][V1 + '/queue']['get']
    assert {name for option in queue['security'] for name in option} == {
        'QueueSenseStaffSession',
        'QueueSenseAccessJWT',
    }
    assert queue['responses']['422']['content']['application/json']['schema'][
        '$ref'
    ].endswith('/ApiError')
    assert '/auth/demo' in spec['paths']


def test_login_refresh_single_use_and_revoke(client, test_url):
    response = create(
        client,
        '/auth/login',
        {
            'email': 'reception@staff.example.test',
            'password': PASSWORD,
            'role': 'reception',
        },
    )
    assert response.status_code == 200, response.text
    assert 'HttpOnly' in response.headers['set-cookie']
    first_token = client.cookies[COOKIE]
    identity = response.json()['data']
    assert set(identity) == {'id', 'email', 'role', 'expires_at'}
    barrier = Barrier(2)

    def rotate(_):
        app = create_app(Settings(test_url, (ORIGIN,), automation_enabled=False))
        with TestClient(app) as peer:
            peer.cookies.set(COOKIE, first_token)
            barrier.wait(timeout=10)
            result = create(peer, '/auth/refresh')
            return result.status_code, result.json(), result.cookies.get(COOKIE)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(rotate, range(2)))
    assert sorted(status for status, _, _ in results) == [200, 401]
    _, updated, replacement = next(item for item in results if item[0] == 200)
    assert updated['data'] == identity and replacement != first_token
    assert_error(client.get(V1 + '/doctors'), 401, 'unauthenticated')
    client.cookies.clear()
    client.cookies.set(COOKIE, replacement)
    assert client.get('/auth/me').json()['role'] == 'reception'
    logout = create(client, '/auth/logout')
    assert logout.status_code == 204 and logout.content == b''
    assert 'Max-Age=0' in logout.headers['set-cookie']
    client.cookies.clear()
    client.cookies.set(COOKIE, replacement)
    assert_error(create(client, '/auth/refresh'), 401, 'unauthenticated')
    assert create(client, '/auth/logout').status_code == 204


def test_v1_safe_errors_and_legacy_error_compatibility(client):
    denied = client.post(V1 + '/auth/logout')
    assert_error(denied, 403, 'forbidden')
    invalid = create(
        client,
        '/auth/login',
        {
            'email': 'test@example.test',
            'password': 'never-echo-this',
            'role': 'invalid-secret-role',
            'extra-secret-field': 'extra-secret-value',
        },
    )
    assert_error(invalid, 422, 'validation_error')
    assert all(
        secret not in invalid.text
        for secret in (
            'never-echo-this',
            'invalid-secret-role',
            'extra-secret-field',
            'extra-secret-value',
        )
    )
    assert_error(client.get(V1 + '/missing'), 404, 'not_found')
    result = client.put(V1 + '/queue', headers=ORIGIN_HEADERS)
    assert_error(result, 405, 'method_not_allowed')
    assert 'Allow' in result.headers
    assert (
        client.post('/auth/logout').json()['detail'] == 'Request origin is not allowed.'
    )


def test_patient_registry_pagination_updates_and_permissions(client):
    assert login(client, 'admin').status_code == 200
    first = create(client, '/patients', {'external_id': ' mrn-2 '})
    assert first.status_code == 201
    second = create(client, '/patients', {'external_id': 'MRN-9'})
    assert second.status_code == 201
    assert create(client, '/patients', {'external_id': 'MRN-2'}).json() == first.json()
    patient = first.json()['data']
    path = f'/patients/{patient["id"]}'
    assert first.headers['location'] == V1 + path
    assert client.get(V1 + path).json() == first.json()

    page = client.get(V1 + '/patients?direction=desc&page_size=1').json()
    assert page == {
        'data': [second.json()['data']],
        'pagination': {'page': 1, 'page_size': 1, 'total': 2, 'pages': 2},
    }
    assert client.get(V1 + '/patients?page=3&page_size=1').json()['data'] == []
    assert_error(update(client, path, {'external_id': 'MRN-9'}), 409, 'conflict')
    corrected = update(client, path, {'external_id': 'mrn-3'})
    assert corrected.json()['data'] == {'id': patient['id'], 'external_id': 'MRN-3'}
    assert client.get(V1 + '/patients?external_id=mrn-3').json()['data'] == [
        corrected.json()['data']
    ]
    assert_error(client.get(V1 + '/patients/' + str(uuid4())), 404, 'not_found')
    assert_error(client.get(V1 + '/patients?page_size=101'), 422, 'validation_error')
    assert login(client, 'reception').status_code == 200
    assert client.get(V1 + path).status_code == 200
    assert_error(update(client, path, {'external_id': 'MRN-4'}), 403, 'forbidden')
    assert login(client, 'doctor').status_code == 200
    assert_error(client.get(V1 + '/patients'), 403, 'forbidden')


def test_queue_filters_history_state_and_private_fields(client, clinic):
    department, staff = clinic
    base = {'department_id': department['id']}
    standard = create(client, '/queue', base)
    expedited = create(
        client,
        '/queue',
        {
            **base,
            'priority_class': 'expedited',
            'priority_reason': 'Private policy reference',
        },
    )
    assert standard.status_code == expedited.status_code == 201
    first_id = standard.json()['data']['id']
    fast_id = expedited.json()['data']['id']
    assert 'Private policy reference' not in expedited.text
    assert not {
        'public_key',
        'patient_id',
        'synthetic_patient_id',
        'priority_reason',
    }.intersection(expedited.json()['data'])
    assert expedited.headers['location'] == f'{V1}/queue/{fast_id}'
    assert client.get(expedited.headers['location']).json() == expedited.json()

    page = client.get(
        V1 + '/queue',
        params={'department_id': department['id'], 'page_size': 1, 'status': 'waiting'},
    ).json()
    assert [row['id'] for row in page['data']] == [fast_id]
    assert page['pagination']['total'] == 2
    ascending = client.get(
        V1 + '/queue', params={'sort': 'token', 'direction': 'asc'}
    ).json()
    assert [row['id'] for row in ascending['data']] == [first_id, fast_id]
    path = f'/queue/{fast_id}'
    assert_error(update(client, path, {'status': 'completed'}), 409, 'conflict')
    for status in ('called', 'in_service', 'completed'):
        body = {'status': status}
        if status == 'called':
            body['staff_id'] = staff['id']
        result = update(client, path, body)
        assert result.status_code == 200, result.text
        assert result.json()['data']['status'] == status
    history = client.get(V1 + path + '/history?page_size=2&page=2').json()
    assert [event['event_type'] for event in history['data']] == [
        'service_start',
        'completed',
    ]
    assert history['pagination']['total'] == 4
    assert_error(client.get(V1 + f'/queue/{uuid4()}/history'), 404, 'not_found')
    assert login(client, 'manager').status_code == 200
    assert_error(
        update(client, f'/queue/{first_id}', {'status': 'cancelled'}), 403, 'forbidden'
    )


def test_doctor_directory_schedule_and_analytics(client, clinic):
    department, doctor = clinic
    day = datetime.now(CLINIC_TIMEZONE).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    schedule = client.post(
        f'/admin/staff/{doctor["id"]}/schedule',
        json={
            'start_at': day.isoformat(),
            'end_at': (day + timedelta(hours=2)).isoformat(),
        },
        headers=ORIGIN_HEADERS,
    )
    assert schedule.status_code == 200
    directory = client.get(
        V1 + '/doctors', params={'department_id': department['id'], 'active': 'true'}
    ).json()
    record = directory['data'][0]
    assert record['availability'] == 'available' and 'user_id' not in record
    doctor_path = f'{V1}/doctors/{doctor["id"]}'
    assert client.get(doctor_path).json() == {'data': record}
    params = {'start': day.date().isoformat(), 'end': day.date().isoformat()}
    assert (
        client.get(doctor_path + '/schedule', params=params).json()['pagination'][
            'total'
        ]
        == 1
    )
    assert_error(client.get(doctor_path + '/schedule'), 422, 'validation_error')

    assert (
        create(client, '/queue', {'department_id': department['id']}).status_code == 201
    )
    assert login(client, 'manager').status_code == 200
    params['department_id'] = department['id']
    waiting = client.get(V1 + '/analytics/waiting-time', params=params).json()['data']
    assert waiting == {
        'measured_waits': 0,
        'average_wait': None,
        'median_wait': None,
        'p90_wait': None,
    }
    performance = client.get(V1 + '/analytics/queue-performance', params=params).json()[
        'data'
    ]
    assert performance['arrivals'] == performance['waiting'] == 1
    peaks = client.get(V1 + '/analytics/peak-hours', params=params).json()['data']
    assert len(peaks) == 1 and peaks[0]['arrivals'] == 1
    assert_error(
        client.get(
            V1 + '/analytics/waiting-time',
            params={**params, 'hour_from': 15, 'hour_to': 3},
        ),
        422,
        'validation_error',
    )
    assert login(client, 'doctor').status_code == 200
    assert_error(
        client.get(V1 + '/analytics/waiting-time', params=params), 403, 'forbidden'
    )


@pytest.mark.parametrize(
    ('failure', 'status', 'code'),
    [
        (psycopg.OperationalError, 503, 'service_unavailable'),
        (RuntimeError, 500, 'internal_error'),
    ],
)
def test_v1_masks_database_and_internal_failures(
    failure, status, code, monkeypatch, caplog
):
    app = create_app(Settings('unused', (ORIGIN,), automation_enabled=False))
    app.dependency_overrides[current_staff] = lambda: {'role': 'admin'}

    def unavailable(*_args):
        raise failure('private response details')

    monkeypatch.setattr(queue, 'list_records', unavailable)
    with TestClient(app) as browser:
        result = browser.get(V1 + '/queue')
    assert_error(result, status, code)
    assert 'private response details' not in result.text
    assert 'private response details' not in caplog.text

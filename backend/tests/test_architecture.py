"""Regression coverage for router composition and shared backend behavior."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
from threading import Barrier

import psycopg
from fastapi.testclient import TestClient

from backend.api.dependencies import current_user, get_settings
from backend.api.traffic import limit_public_link
from backend.app import COOKIE, Settings, create_app
from backend.core.config import CLINIC_TIMEZONE
from backend.services import queue
from backend.tests.test_auth import ORIGIN, client, test_url
from backend.tests.test_product import clinic, post


def test_router_dependencies_can_be_overridden_independently():
    app = create_app(Settings('unused', (ORIGIN,), automation_enabled=False))
    app.dependency_overrides[get_settings] = lambda: Settings(
        'unused',
        (ORIGIN,),
        demo_enabled=True,
        automation_enabled=False,
    )
    app.dependency_overrides[current_user] = lambda: {
        'permissions': ['account:self'],
        'id': '06f2580a-9e67-4b35-b4ef-9f4012b1dbb1',
        'email': 'doctor@example.test',
        'role': 'doctor',
        'expires_at': datetime.now(CLINIC_TIMEZONE),
    }

    with TestClient(app) as browser:
        assert browser.get('/auth/demo').json() == {'enabled': True}
        assert browser.get('/auth/workspace/doctor').json()['user']['role'] == 'doctor'
        assert browser.get('/auth/workspace/admin').status_code == 403
        assert browser.get('/auth/workspace/invalid-role').status_code == 422


def test_db_error_uses_route_template_and_keeps_safe_http_contract(monkeypatch, caplog):
    private_key = 'synthetic-private-key-' + 'a' * 24

    @contextmanager
    def unavailable(_settings):
        raise psycopg.OperationalError(f'Private connection message for {private_key}')
        yield

    monkeypatch.setattr(queue, 'connection', unavailable)
    caplog.set_level(logging.ERROR, logger='queuesense.api')
    app = create_app(Settings('unused', (ORIGIN,), automation_enabled=False))
    app.dependency_overrides[limit_public_link] = lambda: None

    with TestClient(app) as browser:
        response = browser.get(f'/patient/{private_key}')

    assert response.status_code == 503
    assert (
        response.json()['detail']
        == 'The database service is temporarily unavailable. Please try again.'
    )
    assert response.json()['request_id'] == response.headers['X-Request-ID']
    assert response.headers['Cache-Control'] == 'no-store'
    assert private_key not in caplog.text
    assert private_key not in response.text
    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == 'queuesense.api'
    ]
    assert events == [
        {
            'event': 'database_unavailable',
            'route': '/patient/{key}',
            'method': 'GET',
            'request_id': response.headers['X-Request-ID'],
            'error_type': 'OperationalError',
        }
    ]


def test_live_and_paged_queue_share_visit_payload_and_exclude_private_links(
    client, clinic
):
    department, _ = clinic
    created = post(client, '/queue/check-in', {'department_id': department['id']})
    assert created.status_code == 201
    query = f'?department={department["id"]}'
    live = client.get('/queue/live' + query)
    paged = client.get('/queue/page' + query)
    assert live.status_code == paged.status_code == 200
    live_rows, paged_rows = live.json()['tokens'], paged.json()['rows']
    assert live_rows == paged_rows
    assert live_rows[0]['id'] == created.json()['id']
    assert live_rows[0]['position'] == 1
    assert 'public_key' not in live_rows[0]


def test_concurrent_overlapping_shifts_keep_one_schedule(client, clinic, test_url):
    _, staff = clinic
    session = client.cookies[COOKIE]
    start = (datetime.now(CLINIC_TIMEZONE) + timedelta(days=1)).replace(
        hour=9,
        minute=0,
        second=0,
        microsecond=0,
    )
    path = f'/admin/staff/{staff["id"]}/schedule'
    ready = Barrier(2)

    def schedule(offset):
        shift = start + timedelta(minutes=offset)
        payload = {
            'start_at': shift.isoformat(),
            'end_at': (shift + timedelta(hours=2)).isoformat(),
        }
        app = create_app(Settings(test_url, (ORIGIN,), automation_enabled=False))
        with TestClient(app) as browser:
            browser.cookies.set(COOKIE, session)
            ready.wait(timeout=10)
            return post(browser, path, payload).status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(schedule, (0, 30))) == [200, 409]
    day = start.date()
    result = client.get(f'/schedules?start={day}&end={day}')
    assert result.status_code == 200
    assert len(result.json()) == 1

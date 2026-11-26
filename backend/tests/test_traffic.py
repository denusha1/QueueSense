"""Verify shared budgets, HTTP 429 and isolation between request classes."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import sleep
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from backend.core.errors import ServiceError
from backend.database import connection
from backend.repositories import traffic
from backend.services import traffic as staff_traffic
from backend.tests.test_auth import client, login, test_url  # noqa: F401
from backend.tests.test_choreo_gateway import (
    ASSERTION_HEADER,
    PATH,
    app_for,
    assertion,
    last_monday,
    rsa_key,  # noqa: F401
)
from backend.tests.test_product import clinic, post  # noqa: F401


def away_from_boundary(settings):
    with connection(settings) as conn:
        seconds = conn.execute(
            'SELECT extract(second FROM now()) AS seconds'
        ).fetchone()['seconds']
    if seconds >= 58:
        sleep(float(60 - seconds) + 0.1)


def test_budget_atomic_across_connections_and_resets(client, test_url):
    settings = client.app.state.settings
    away_from_boundary(settings)
    subject = uuid4()
    gate = Barrier(8)

    def attempt(_):
        gate.wait(timeout=5)
        try:
            with connection(settings) as conn:
                traffic.consume(conn, 'test-concurrent', subject, 3)
            return 200, None
        except ServiceError as exc:
            return exc.status_code, int(exc.headers['Retry-After'])

    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(attempt, range(8)))
    assert results.count((200, None)) == 3
    assert (
        len([1 for status, after in results if status == 429 and 1 <= after <= 60]) == 5
    )

    with psycopg.connect(test_url) as db:
        db.execute(
            'UPDATE api_traffic_budgets SET window_start=window_start-60 WHERE subject=%s',
            (subject,),
        )
    with connection(settings) as conn:
        traffic.consume(conn, 'test-concurrent', subject, 3)
        assert (
            conn.execute(
                'SELECT requests FROM api_traffic_budgets WHERE subject=%s', (subject,)
            ).fetchone()['requests']
            == 1
        )


def test_staff_budgets_follow_account_across_routes(client, monkeypatch):
    monkeypatch.setitem(staff_traffic.STAFF_LIMITS, 'reception', (2, 120))
    away_from_boundary(client.app.state.settings)
    assert login(client, 'reception').status_code == 200
    assert client.get('/api/v1/doctors').status_code == 200
    assert client.get('/departments').status_code == 200
    assert_limited(client.get('/api/v1/doctors'))
    assert login(client, 'doctor').status_code == 200
    assert client.get('/api/v1/doctors').status_code == 200


def test_link_budget_spans_reads_but_keeps_private_links_separate(
    client, clinic, test_url
):
    dep, _ = clinic
    first, second = [
        post(client, '/queue/check-in', {'department_id': dep['id']}).json()
        for _ in range(2)
    ]
    away_from_boundary(client.app.state.settings)
    with psycopg.connect(test_url) as db:
        db.execute(
            """INSERT INTO api_traffic_budgets
            VALUES ('link-read', %s, floor(extract(epoch from now())/60)::bigint*60, 39)""",
            (first['id'],),
        )
    client.cookies.clear()
    path = '/patient/' + first['public_key']
    assert client.get(path).status_code == 200
    assert_limited(client.get(path + '/notifications'))
    assert client.get('/patient/' + second['public_key']).status_code == 200
    assert first['public_key'] not in client.get(path).text


def assert_limited(response):
    assert response.status_code == 429, response.text
    assert response.json()['error']['code'] == 'rate_limited'
    assert 1 <= int(response.headers['Retry-After']) <= 60
    assert response.headers['Cache-Control'] == 'no-store'


def test_admin_budget_is_independent_from_regular_reads(client, test_url):
    signed_in = login(client, 'admin')
    assert signed_in.status_code == 200
    away_from_boundary(client.app.state.settings)
    with psycopg.connect(test_url) as db:
        db.execute(
            """INSERT INTO api_traffic_budgets
            VALUES ('admin-read', %s, floor(extract(epoch from now())/60)::bigint*60, 60)""",
            (signed_in.json()['id'],),
        )
    assert_limited(client.get('/admin/users'))
    assert client.get('/departments').status_code == 200


def test_partner_quota_returns_origin_429(client, test_url, rsa_key, monkeypatch):
    dept = uuid4()
    app = app_for(test_url, dept, rsa_key, monkeypatch)
    away_from_boundary(app.state.settings)
    with psycopg.connect(test_url) as db:
        db.execute(
            """INSERT INTO api_traffic_budgets
            VALUES ('partner-weekly-read', %s, floor(extract(epoch from now())/60)::bigint*60, 30)""",
            (dept,),
        )
    with TestClient(app) as api:
        response = api.get(
            PATH,
            params={'department_id': str(dept), 'week_start': last_monday()},
            headers={ASSERTION_HEADER: assertion(rsa_key)},
        )
    assert_limited(response)
    assert 'detail' not in response.json()

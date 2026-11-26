"""Verify staff grants and resource ownership across the public and staff APIs."""

from datetime import datetime
from uuid import uuid4

import psycopg
import pytest

from backend.core.config import CLINIC_TIMEZONE
from backend.tests.test_api_v1 import assert_error, create, update
from backend.tests.test_arrivals import publish
from backend.tests.test_auth import client, login, test_url  # noqa: F401
from backend.tests.test_planning import another
from backend.tests.test_product import clinic, patch, post  # noqa: F401

V1 = '/api/v1'


@pytest.mark.parametrize(
    ('role', 'can_read_queue', 'can_read_registry', 'can_read_analytics'),
    [
        ('admin', True, True, True),
        ('reception', True, True, False),
        ('doctor', True, False, False),
        ('manager', False, False, True),
    ],
)
def test_staff_permission_matrix(
    client, clinic, role, can_read_queue, can_read_registry, can_read_analytics
):
    assert login(client, role).status_code == 200
    day = datetime.now(CLINIC_TIMEZONE).date()
    checks = {
        V1 + '/queue': can_read_queue,
        '/queue/live': can_read_queue,
        '/queue/page': can_read_queue,
        V1 + '/patients': can_read_registry,
        V1 + f'/analytics/waiting-time?start={day}&end={day}': can_read_analytics,
        V1 + '/doctors': True,
        '/auth/me': True,
        '/admin/users': role == 'admin',
        '/audit': role == 'admin',
    }
    for path, permitted in checks.items():
        result = client.get(path)
        if permitted:
            assert result.status_code == 200, (path, result.text)
            assert 'permissions' not in result.text
        else:
            assert_error(result, 403, 'forbidden')

    if role == 'manager':
        query = {'start': day, 'end': day, 'report_type': 'operational'}
        assert client.get('/reports/export', params=query).status_code == 200
        denied = client.get(
            '/reports/export', params={**query, 'report_type': 'visits'}
        )
        assert_error(denied, 403, 'forbidden')

    if role != 'admin':
        assert_error(post(client, '/alerts/refresh'), 403, 'forbidden')
        assert_error(
            post(client, '/data/import', {'csv_text': 'sample', 'dry_run': True}),
            403,
            'forbidden',
        )
        assert_error(
            post(
                client,
                '/admin/users',
                {
                    'email': 'elevation@example.test',
                    'role': 'admin',
                    'password': 'Synthetic-password-2026',
                },
            ),
            403,
            'forbidden',
        )


def test_doctor_can_claim_next_but_cannot_target_unassigned_or_other_visits(
    client, clinic
):
    dep, doctor = clinic
    other = another(client, dep)
    foreign = post(client, '/queue/check-in', {'department_id': dep['id']}).json()
    assert post(client, f'/staff/{other["id"]}/call-next').status_code == 200
    waiting = create(
        client,
        '/queue',
        {
            'department_id': dep['id'],
            'priority_class': 'expedited',
            'priority_reason': 'Internal authorization reference',
        },
    )
    assert waiting.status_code == 201, waiting.text
    waiting_id = waiting.json()['data']['id']
    assert login(client, 'doctor').status_code == 200

    for token_id in (foreign['id'], waiting_id, str(uuid4())):
        assert_error(client.get(f'{V1}/queue/{token_id}'), 404, 'not_found')
        assert_error(client.get(f'{V1}/queue/{token_id}/history'), 404, 'not_found')
        assert_error(
            update(
                client,
                f'/queue/{token_id}',
                {
                    'status': 'called',
                    'staff_id': doctor['id'],
                },
            ),
            404,
            'not_found',
        )
        assert_error(
            patch(
                client,
                f'/queue/{token_id}/status',
                {
                    'status': 'cancelled',
                },
            ),
            404,
            'not_found',
        )
    assert_error(client.get(f'/queue/{waiting_id}/private-link'), 403, 'forbidden')
    assert_error(post(client, f'/staff/{other["id"]}/call-next'), 403, 'forbidden')
    assert_error(
        post(
            client,
            '/planning/doctors',
            {
                'department_id': dep['id'],
                'token_id': waiting_id,
            },
        ),
        404,
        'not_found',
    )
    assert_error(
        client.get('/planning/balance', params={'department_id': dep['id']}),
        403,
        'forbidden',
    )

    claimed = post(client, f'/staff/{doctor["id"]}/call-next')
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()['id'] == waiting_id
    assert {
        'public_key',
        'priority_reason',
        'patient_id',
        'synthetic_patient_id',
    }.isdisjoint(claimed.json())
    collection = client.get(V1 + '/queue').json()
    assert collection['pagination']['total'] == 1
    assert [row['id'] for row in collection['data']] == [waiting_id]
    assert (
        client.get(V1 + '/queue', params={'staff_id': other['id']}).json()['data'] == []
    )
    assert client.get(f'{V1}/queue/{waiting_id}/history').status_code == 200
    for sort in ('arrival', 'wait', 'token'):
        page = client.get('/queue/page', params={'sort': sort}).json()
        assert page['total'] == page['department_total'] == 1
        assert [row['id'] for row in page['rows']] == [waiting_id]
        assert page['rows'][0]['priority_reason'] == ''
    assert [row['id'] for row in client.get('/queue/live').json()['tokens']] == [
        waiting_id
    ]
    assert (
        update(client, f'/queue/{waiting_id}', {'status': 'in_service'}).status_code
        == 200
    )

    assert (
        login(client, 'doctor', email='doctor@demo.queuesense.test').status_code == 200
    )
    assert client.get(V1 + '/queue').json()['data'] == []
    assert_error(client.get(f'{V1}/queue/{waiting_id}'), 404, 'not_found')


def test_capabilities_are_object_and_audience_specific(client, clinic, test_url):
    dep, _ = clinic
    visits = [
        post(client, '/queue/check-in', {'department_id': dep['id']}).json()
        for _ in range(2)
    ]
    slot = publish(client, dep, capacity=2)
    bookings = [
        post(client, '/appointments', {'slot_id': slot['id']}).json() for _ in range(2)
    ]
    with psycopg.connect(test_url) as conn:
        token_notification = conn.execute(
            'INSERT INTO notifications(department_id,token_id,audience,kind,message,event_key) '
            "VALUES(%s,%s,'patient','test','Synthetic message',%s) RETURNING id",
            (dep['id'], visits[0]['id'], str(uuid4())),
        ).fetchone()[0]
        booking_notification = conn.execute(
            'INSERT INTO notifications(department_id,appointment_id,audience,kind,message,event_key) '
            "VALUES(%s,%s,'appointment','test','Synthetic message',%s) RETURNING id",
            (dep['id'], bookings[0]['id'], str(uuid4())),
        ).fetchone()[0]
    assert_error(
        post(client, f'/notifications/{token_notification}/read'), 404, 'not_found'
    )
    client.cookies.clear()

    for prefix, records, notification_id in (
        ('/patient/', visits, token_notification),
        ('/self-checkin/', bookings, booking_notification),
    ):
        first, second = [prefix + row['public_key'] for row in records]
        assert client.get(first).status_code == 200
        feed = client.get(second + '/notifications')
        assert feed.status_code == 200, feed.text
        notifications = feed.json()
        if prefix == '/self-checkin/':
            notifications = notifications['notifications']
        assert str(notification_id) not in {n['id'] for n in notifications}
        suffix = f'/notifications/{notification_id}/read'
        assert_error(post(client, second + suffix), 404, 'not_found')
        assert post(client, first + suffix).status_code == 200
        assert_error(client.get(prefix + records[0]['id']), 404, 'not_found')

    assert_error(client.get('/patient/' + bookings[0]['public_key']), 404, 'not_found')
    assert_error(
        client.get('/self-checkin/' + visits[0]['public_key']), 404, 'not_found'
    )
    assert_error(
        client.get(
            V1 + '/queue',
            headers={
                'Authorization': 'Bearer ' + visits[0]['public_key'],
            },
        ),
        401,
        'unauthenticated',
    )


def test_permission_removal_is_applied_to_an_existing_session(client, test_url):
    assert login(client, 'reception').status_code == 200
    assert client.get(V1 + '/queue').status_code == 200
    with psycopg.connect(test_url) as conn:
        conn.execute(
            "DELETE FROM role_permissions WHERE role_code='reception' AND permission_code='queue:read'"
        )
    try:
        assert_error(client.get(V1 + '/queue'), 403, 'forbidden')
    finally:
        with psycopg.connect(test_url) as conn:
            conn.execute(
                "INSERT INTO role_permissions VALUES ('reception','queue:read')"
            )

"""PostgreSQL-backed registration and duplicate protection through the staff API."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from backend.app import COOKIE, Settings, create_app
from backend.core.config import CLINIC_TIMEZONE
from backend.tests.test_auth import ORIGIN, client, login, test_url
from backend.tests.test_product import clinic, patch, post


def test_concurrent_patient_registration_and_token_issuance(client, clinic, test_url):
    department, _ = clinic
    admin_token = client.cookies[COOKIE]
    assert login(client, 'reception').status_code == 200
    # Login replaces the cookie's previous session. Start a separate admin session
    # so two currently active staff identities make the concurrent requests.
    with TestClient(
        create_app(Settings(test_url, (ORIGIN,), automation_enabled=False))
    ) as admin:
        assert login(admin, 'admin').status_code == 200
        assert admin.cookies[COOKIE] != admin_token
        peers = (admin, client)

        def together(path, payloads):
            start = Barrier(2)

            def submit(args):
                browser, payload = args
                start.wait(timeout=10)
                return post(browser, path, payload)

            with ThreadPoolExecutor(max_workers=2) as pool:
                return list(pool.map(submit, zip(peers, payloads, strict=True)))

        registrations = together(
            '/patients',
            ({'external_id': ' mrn-2026.1 '}, {'external_id': 'MRN-2026.1'}),
        )
        assert sorted(result.status_code for result in registrations) == [200, 201]
        first, second = (result.json() for result in registrations)
        assert first == second
        patient_id = first['id']

        checkin = {'department_id': department['id'], 'patient_id': patient_id}
        tokens = together('/queue/check-in', (checkin, checkin))
        assert sorted(result.status_code for result in tokens) == [201, 409]
        token = next(result.json() for result in tokens if result.status_code == 201)
        assert 'patient_id' not in token

        with psycopg.connect(test_url) as conn:
            assert (
                conn.execute(
                    'SELECT count(*) FROM patients WHERE id=%s AND external_id=%s',
                    (patient_id, 'MRN-2026.1'),
                ).fetchone()[0]
                == 1
            )
            assert (
                conn.execute(
                    'SELECT count(*) FROM queue_tokens WHERE patient_id=%s',
                    (patient_id,),
                ).fetchone()[0]
                == 1
            )
            assert (
                conn.execute(
                    'SELECT count(*) FROM audit_logs WHERE action=%s AND entity_id=%s',
                    ('register_patient', patient_id),
                ).fetchone()[0]
                == 1
            )

        assert (
            patch(
                client, f'/queue/{token["id"]}/status', {'status': 'cancelled'}
            ).status_code
            == 200
        )
        replacement = post(client, '/queue/check-in', checkin)
        assert replacement.status_code == 201, replacement.text
        assert replacement.json()['token_no'] == token['token_no'] + 1
        assert 'patient_id' not in client.get('/patient/' + token['public_key']).json()


def test_registration_requires_staff_permission_and_valid_identifier(client, clinic):
    department, _ = clinic
    assert post(client, '/patients', {'external_id': 'has spaces'}).status_code == 422
    assert post(client, '/patients', {'external_id': 'mrn-ß'}).status_code == 422
    assert (
        post(
            client,
            '/queue/check-in',
            {
                'department_id': department['id'],
                'patient_id': str(uuid4()),
            },
        ).status_code
        == 404
    )
    for role in ('doctor', 'manager'):
        assert login(client, role).status_code == 200
        assert post(client, '/patients', {'external_id': 'NO-GRANT'}).status_code == 403
    client.cookies.clear()
    assert post(client, '/patients', {'external_id': 'NO-SESSION'}).status_code == 401


def test_identified_booking_checkin_reuses_the_linked_token(client, clinic, test_url):
    department, _ = clinic
    patient = post(client, '/patients', {'external_id': 'BOOK-01'}).json()
    now = datetime.now(CLINIC_TIMEZONE)
    slot_time = now.replace(second=0, microsecond=0) + timedelta(
        minutes=30 - now.minute % 30
    )
    slot = post(
        client,
        '/appointments/slots',
        {
            'department_id': department['id'],
            'starts_at': slot_time.isoformat(),
            'capacity': 3,
        },
    )
    assert slot.status_code == 201, slot.text
    payload = {'slot_id': slot.json()['id'], 'patient_id': patient['id']}
    booked = post(client, '/appointments', payload)
    assert booked.status_code == 201 and 'patient_id' not in booked.json()
    assert post(client, '/appointments', payload).status_code == 409
    booking = booked.json()

    arrival_path = '/self-checkin/' + booking['public_key']
    assert 'patient_id' not in client.get(arrival_path).json()
    arrival = post(client, arrival_path, {'request_id': str(uuid4())})
    assert arrival.status_code == 200, arrival.text
    retry = post(client, arrival_path, {'request_id': str(uuid4())})
    assert retry.status_code == 200 and retry.json() == arrival.json()
    assert (
        'patient_id'
        not in client.get('/patient/' + arrival.json()['patient_key']).json()
    )
    assert (
        post(
            client,
            '/queue/check-in',
            {
                'department_id': department['id'],
                'patient_id': patient['id'],
            },
        ).status_code
        == 409
    )

    with psycopg.connect(test_url) as conn:
        assert conn.execute(
            'SELECT a.patient_id::text,t.patient_id::text,t.public_key FROM appointments a '
            'JOIN queue_tokens t ON t.id=a.token_id WHERE a.id=%s',
            (booking['id'],),
        ).fetchone() == (patient['id'], patient['id'], arrival.json()['patient_key'])

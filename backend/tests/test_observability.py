"""Metrics and logs preserve request correlation without sensitive labels."""

import json
import logging
import secrets
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg

from backend.api.endpoints import health
from backend.app import create_app
from backend.core.config import Settings
from backend.core.rate_limit import SlidingWindowLimiter


def test_private_metrics_request_telemetry_and_readiness(monkeypatch, caplog):
    secret = secrets.token_urlsafe(32)
    request_id = str(uuid4())
    trace = 'b' * 32
    path_value = 'test-path-must-stay-private'
    token_value = 'test-credential-must-stay-private'

    def fail(_):
        raise psycopg.OperationalError('SENSITIVE SQL ' + path_value)

    monkeypatch.setattr(health, 'check_database', fail)
    caplog.set_level(logging.INFO, logger='queuesense.requests')
    app = create_app(Settings(
        'unused', ('http://testserver',), automation_enabled=False,
        metrics_bearer_token=secret, request_logs_enabled=True,
    ))
    app.state.public_status_limiter = SlidingWindowLimiter(limit=1, window_seconds=60)

    with TestClient(app) as client:
        health_response = client.get('/health', headers={
            'X-Request-ID': request_id, 'traceparent': f'00-{trace}-{"c" * 16}-00',
        })
        assert health_response.status_code == 503
        assert health_response.json()['request_id'] == request_id
        assert 'SENSITIVE SQL' not in health_response.text
        assert client.get('/health/live').status_code == 200
        assert client.get('/unknown/' + path_value, headers={'Authorization': token_value}).status_code == 404
        assert client.get('/patient/invalid').status_code in (404, 422)
        assert client.get('/patient/invalid').status_code == 429
        assert client.get('/internal/metrics').status_code == 401
        assert client.get('/internal/metrics', headers={'Authorization': 'Bearer other'}).status_code == 401
        assert '/internal/metrics' not in client.get('/openapi.json').json()['paths']
        exported = client.get('/internal/metrics', headers={'Authorization': 'Bearer ' + secret})
        assert exported.status_code == 200

    for forbidden in (secret, path_value, token_value, 'SENSITIVE SQL'):
        assert forbidden not in exported.text
        assert forbidden not in caplog.text
    assert 'queuesense_http_requests_total{method="GET",route="/health",status="503"} 1.0' in exported.text
    assert 'queuesense_http_requests_total{method="GET",route="<unmatched>",status="429"} 1.0' in exported.text
    assert 'queuesense_http_request_duration_seconds_bucket' in exported.text
    events = [json.loads(record.getMessage()) for record in caplog.records if record.name == 'queuesense.requests']
    recorded = next(event for event in events if event['request_id'] == request_id)
    assert recorded['trace_id'] == trace and recorded['status'] == 503
    assert recorded['duration_ms'] >= 0


def test_metrics_are_disabled_without_a_token():
    app = create_app(Settings('unused', ('http://testserver',), automation_enabled=False))
    with TestClient(app) as client:
        assert client.get('/internal/metrics').status_code == 404

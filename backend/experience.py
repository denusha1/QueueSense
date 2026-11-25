"""Patient experience and bounded, authenticated dependency probes."""

import math
import time
from datetime import datetime, timezone

import psycopg
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.errors import ServiceError
from backend.core.security import MANAGERS, require
from backend.database import connection
from backend.repositories.audit import audit


class Feedback(BaseModel):
    model_config = ConfigDict(extra='forbid')
    rating: int = Field(ge=1, le=5, strict=True)
    comment: str = Field(default='', max_length=1000)

    @field_validator('comment')
    @classmethod
    def clean_comment(cls, value):
        if any(ord(c) < 32 and c not in '\n\r\t' for c in value):
            raise ValueError('Comment contains invalid characters.')
        return value.strip()


def feedback_status(settings, key):
    with connection(settings) as conn:
        row = conn.execute(
            'SELECT t.status, f.rating FROM queue_tokens t LEFT JOIN patient_feedback f ON f.token_id=t.id WHERE t.public_key=%s',
            (key,),
        ).fetchone()
        if not row:
            raise ServiceError(404, 'Token not found.')
        return {
            'eligible': row['status'] == 'completed',
            'submitted': row['rating'] is not None,
        }


def submit_feedback(settings, body, key):
    with connection(settings) as conn:
        token = conn.execute(
            'SELECT id,status FROM queue_tokens WHERE public_key=%s FOR UPDATE', (key,)
        ).fetchone()
        if not token:
            raise ServiceError(404, 'Token not found.')
        if token['status'] != 'completed':
            raise ServiceError(409, 'Feedback opens after your visit is complete.')
        row = conn.execute(
            'INSERT INTO patient_feedback(token_id,rating,comment) VALUES(%s,%s,%s) ON CONFLICT(token_id) DO NOTHING RETURNING id',
            (token['id'], body.rating, body.comment),
        ).fetchone()
        if not row:
            raise ServiceError(
                409, 'Feedback has already been submitted for this visit.'
            )
        audit(
            conn,
            None,
            'submit_feedback',
            'queue_token',
            token['id'],
            actor_type='patient',
        )
    return {'submitted': True}


def summary(settings, start, end, department, user):
    require(user, MANAGERS)
    if start > end or (end - start).days > 366:
        raise ServiceError(422, 'Choose a date range of at most 366 days.')
    # Cohort is visit date in the clinic timezone, matching waiting-time analytics.
    base = """FROM patient_feedback f JOIN queue_tokens t ON t.id=f.token_id JOIN departments d ON d.id=t.department_id
    WHERE (t.check_in_at AT TIME ZONE d.timezone)::date BETWEEN %s AND %s AND (%s::uuid IS NULL OR t.department_id=%s)"""
    params = (start, end, department, department)
    with connection(settings) as conn:
        totals = conn.execute(
            'SELECT count(*) AS responses, avg(f.rating) AS average_rating, avg(extract(epoch FROM(t.service_start_at-t.check_in_at))/60) AS average_wait, corr(f.rating::float, extract(epoch FROM(t.service_start_at-t.check_in_at))::float/60) AS wait_rating_correlation '
            + base,
            params,
        ).fetchone()
        bands = conn.execute(
            "SELECT CASE WHEN t.service_start_at-t.check_in_at < interval '15 minutes' THEN 'Under 15 min' WHEN t.service_start_at-t.check_in_at < interval '30 minutes' THEN '15–30 min' ELSE '30+ min' END AS wait_band, count(*) AS responses,avg(f.rating) AS average_rating "
            + base
            + ' GROUP BY 1 ORDER BY min(t.service_start_at-t.check_in_at)',
            params,
        ).fetchall()
        comments = conn.execute(
            'SELECT f.rating,f.comment,f.created_at,d.name AS department '
            + base
            + " AND f.comment<>'' ORDER BY f.created_at DESC LIMIT 100",
            params,
        ).fetchall()
    return dict(
        summary=totals,
        bands=bands,
        comments=comments,
        note='Voluntary responses may be biased. Correlation does not establish causation; it is unavailable when fewer than two variable pairs exist. Comments are limited to the latest 100 in this cohort.',
    )


def services(settings, user):
    require(user, MANAGERS)
    checks = [
        {
            'service': 'Application API',
            'status': 'healthy',
            'detail': 'Request handled successfully.',
            'latency_ms': 0,
        }
    ]
    started = time.monotonic()
    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
            conn.execute("SET statement_timeout='3000ms'")
            conn.execute('SELECT 1').fetchone()
            # Real-time notifications use PostgreSQL LISTEN/NOTIFY, not an external provider.
            conn.execute('LISTEN queuesense_health_probe')
            conn.execute("SELECT pg_notify('queuesense_health_probe','probe')")
            conn.commit()
            delivered = next(conn.notifies(timeout=1, stop_after=1), None) is not None
        checks.append(
            dict(
                service='Database',
                status='healthy',
                detail='Connection and query succeeded.',
                latency_ms=round((time.monotonic() - started) * 1000, 1),
            )
        )
        checks.append(
            dict(
                service='Notification service',
                status='healthy' if delivered else 'unavailable',
                detail='PostgreSQL LISTEN/NOTIFY delivery verified.'
                if delivered
                else 'Notification probe did not arrive.',
            )
        )
    except psycopg.Error:
        checks.extend(
            [
                dict(
                    service='Database',
                    status='unavailable',
                    detail='Database probe failed.',
                ),
                dict(
                    service='Notification service',
                    status='unavailable',
                    detail='Database notification transport unavailable.',
                ),
            ]
        )
    try:
        with connection(settings) as conn:
            heartbeat = conn.execute(
                "SELECT updated_at FROM automation_state WHERE entity_key='worker:heartbeat'"
            ).fetchone()
        fresh = (
            heartbeat
            and (datetime.now(timezone.utc) - heartbeat['updated_at']).total_seconds()
            < 120
        )
        checks.append(
            dict(
                service='Automation worker',
                status='healthy'
                if settings.automation_enabled and fresh
                else 'degraded',
                detail='Reminder and congestion cycle completed within two minutes.'
                if settings.automation_enabled and fresh
                else 'Worker disabled, starting, or last successful cycle is stale.',
            )
        )
    except psycopg.Error:
        checks.append(
            dict(
                service='Automation worker',
                status='unavailable',
                detail='Worker heartbeat could not be checked.',
            )
        )
    started = time.monotonic()
    try:
        from backend.services.prediction import artifact

        stored = artifact()
        if stored is None or stored.get('model') is None:
            checks.append(
                dict(
                    service='Machine learning',
                    status='degraded',
                    detail='Model unavailable; operational baseline is used.',
                )
            )
        else:
            value = stored['model'].predict(
                [
                    dict(
                        department='health-probe',
                        queue_ahead=1,
                        active_staff=1,
                        recent_service=12,
                        arrivals_30m=1,
                        hour=9,
                        weekday=1,
                    )
                ]
            )[0]
            if not math.isfinite(float(value)):
                raise ValueError('Non-finite model prediction')
            checks.append(
                dict(
                    service='Machine learning',
                    status='healthy',
                    detail='In-process model inference succeeded.',
                    latency_ms=round((time.monotonic() - started) * 1000, 1),
                )
            )
    except Exception:
        checks.append(
            dict(
                service='Machine learning',
                status='unavailable',
                detail='Model inference failed.',
            )
        )
    status = 'healthy' if all(c['status'] == 'healthy' for c in checks) else 'degraded'
    return dict(
        status=status,
        checked_at=datetime.now(timezone.utc),
        services=checks,
        notice='On-demand probes cover the live-update transport and automation heartbeat. Notifications are delivered in-app; external SMS/email delivery is not configured.',
    )

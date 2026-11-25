"""Application use cases for reporting operations."""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from backend.core.config import CLINIC_TIMEZONE as TZ
from backend.core.errors import ServiceError
from backend.core.security import MANAGERS, require
from backend.database import connection
from backend.repositories.audit import audit
from backend.services.clinic import active_staff, service_estimate
from backend.services.metrics import analytics, cohort_summary, filters, peak_hours

ROOT = Path(__file__).resolve().parents[2]


def simulate(body):
    capacity = body.staff * 60 / body.service_minutes
    stable = capacity > body.arrivals_per_hour
    clearance = (
        body.queue / (capacity - body.arrivals_per_hour) * 60 if stable else None
    )
    wait = body.queue * body.service_minutes / body.staff
    return dict(
        capacity_per_hour=round(capacity, 1),
        clearance_minutes=round(clearance, 1) if clearance is not None else None,
        estimated_wait=round(wait, 1),
        congestion='high'
        if not stable or wait > 30
        else 'moderate'
        if wait > 15
        else 'low',
        stable=stable,
        assumptions='Constant arrivals and service duration; FIFO; all staff continuously available. Breaks and variability are excluded. An estimate, not a clinical recommendation.',
    )


def summary(settings, start, end, department, staff, weekday, hour_from, hour_to, user):
    require(user, MANAGERS)
    with connection(settings) as conn:
        return analytics(
            conn, start, end, department, staff, weekday, hour_from, hour_to
        )


def simulation(body, user):
    require(user, MANAGERS)
    return simulate(body)


def performance(settings, start, end, department, user):
    require(user, MANAGERS)
    path = ROOT / 'ml/evaluation/results.json'
    if not path.exists():
        raise ServiceError(503, 'Train the model before viewing evaluation results.')
    result = json.loads(path.read_text())
    with connection(settings) as conn:
        from backend.services.monitoring import monitoring

        window_end = end or datetime.now(TZ).date()
        window_start = start or window_end - timedelta(days=89)
        result['live_monitoring'] = monitoring(
            conn, window_start, window_end, department
        )
        result['monitoring'] = result['live_monitoring']['departments']
    return result


def predict(settings, body):
    with connection(settings) as conn:
        from backend.services.prediction import current_prediction

        return current_prediction(
            conn, body.department_id, requirements=body.model_dump()
        )


def alerts(settings):
    with connection(settings) as conn:
        return conn.execute(
            'SELECT a.*,d.name AS department FROM alerts a JOIN departments d ON d.id=a.department_id ORDER BY (a.resolved_at IS NULL) DESC,a.created_at DESC LIMIT 100'
        ).fetchall()


def refresh_alerts(settings, user):
    require(user, MANAGERS)
    with connection(settings) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(72419024)')
        for dep in conn.execute('SELECT * FROM departments WHERE is_active').fetchall():
            waiting = conn.execute(
                "SELECT count(*) AS n FROM queue_tokens WHERE department_id=%s AND status='waiting'",
                (dep['id'],),
            ).fetchone()['n']
            arrivals = conn.execute(
                "SELECT count(*) AS n FROM queue_tokens WHERE department_id=%s AND check_in_at>now()-interval '30 minutes'",
                (dep['id'],),
            ).fetchone()['n']
            recent = conn.execute(
                "SELECT avg(extract(epoch FROM(service_start_at-check_in_at))/60) AS wait FROM queue_tokens WHERE department_id=%s AND service_start_at>now()-interval '60 minutes'",
                (dep['id'],),
            ).fetchone()['wait']
            baseline = conn.execute(
                'SELECT avg(waiting_minutes) AS wait FROM token_durations WHERE department_id=%s',
                (dep['id'],),
            ).fetchone()['wait']
            error = conn.execute(
                "SELECT count(*) AS n,avg(abs(extract(epoch FROM(t.service_start_at-t.check_in_at))/60-p.predicted_wait_minutes)) AS mae FROM predictions p JOIN queue_tokens t ON t.id=p.token_id WHERE t.department_id=%s AND t.service_start_at>now()-interval '1 day'",
                (dep['id'],),
            ).fetchone()
            conditions = [
                (
                    'high_queue',
                    waiting > dep['queue_threshold'],
                    f'{waiting} waiting; threshold {dep["queue_threshold"]}.',
                ),
                (
                    'capacity',
                    arrivals
                    > active_staff(conn, dep['id'])
                    * 30
                    / max(service_estimate(conn, dep['id']), 1),
                    f'{arrivals} arrivals in 30 minutes exceed available service capacity.',
                ),
                (
                    'delay',
                    bool(
                        recent and baseline and recent > max(float(baseline) * 1.5, 20)
                    ),
                    'Recent wait is above the historical baseline.',
                ),
                (
                    'model_error',
                    error['n'] >= 10 and float(error['mae'] or 0) > 15,
                    'Observed prediction error exceeds 15 minutes across at least 10 visits.',
                ),
            ]
            for kind, trigger, message in conditions:
                if trigger:
                    conn.execute(
                        "INSERT INTO alerts(department_id,alert_type,severity,message) VALUES(%s,%s,'warning',%s) ON CONFLICT(department_id,alert_type) WHERE resolved_at IS NULL DO UPDATE SET message=EXCLUDED.message",
                        (dep['id'], kind, message),
                    )
                else:
                    conn.execute(
                        'UPDATE alerts SET resolved_at=now() WHERE department_id=%s AND alert_type=%s AND resolved_at IS NULL',
                        (dep['id'], kind),
                    )
        audit(conn, user, 'refresh_alerts', 'system', uuid.UUID(int=0))
    return {'ok': True}


def resolve_alert(settings, alert_id, user):
    require(user, MANAGERS)
    with connection(settings) as conn:
        row = conn.execute(
            'UPDATE alerts SET resolved_at=coalesce(resolved_at,now()) WHERE id=%s RETURNING id',
            (alert_id,),
        ).fetchone()
        if not row:
            raise ServiceError(404, 'Alert not found.')
        audit(conn, user, 'resolve_alert', 'alert', alert_id)
    return {'ok': True}


def import_data(settings, body, user):
    require(user, MANAGERS)
    from backend.services.importer import import_csv

    with connection(settings) as conn:
        result = import_csv(conn, body.csv_text, body.dry_run)
        if not body.dry_run:
            audit(conn, user, 'import_csv', 'system', uuid.UUID(int=0))
        return result


def export(
    settings,
    start,
    end,
    format,
    report_type,
    department,
    staff,
    weekday,
    hour_from,
    hour_to,
    user,
):
    require(user, MANAGERS)
    from backend.services.reports import render, sections

    with connection(settings) as conn:
        tables = sections(
            conn,
            start,
            end,
            report_type,
            department,
            staff,
            weekday,
            hour_from,
            hour_to,
        )
        if (
            format == 'pdf'
            and report_type == 'visits'
            and len(tables[0]['rows']) > 5000
        ):
            raise ServiceError(
                422,
                'Detailed PDF exceeds 5,000 visits. Narrow the selection or use CSV.',
            )
        cohort = f'Department={department or "all"}; doctor={staff or "all"}; weekday={weekday or "all"}; hours={hour_from}:00-{hour_to}:59'
        content, media = render(tables, format, start, end, report_type, cohort)
        audit(
            conn,
            user,
            'export_' + format,
            'report',
            uuid.UUID(int=0),
            {
                'report_type': report_type,
                'start': str(start),
                'end': str(end),
                'department_id': str(department) if department else None,
                'staff_id': str(staff) if staff else None,
                'weekday': weekday,
                'hour_from': hour_from,
                'hour_to': hour_to,
            },
        )
    return content, media


def cohort_filters(query):
    return filters(
        query.start,
        query.end,
        query.department_id,
        query.staff_id,
        query.weekday,
        query.hour_from,
        query.hour_to,
    )


def cohort_metrics(settings, user, query):
    require(user, MANAGERS)
    where, args = cohort_filters(query)
    with connection(settings) as conn:
        return cohort_summary(conn, where, args)


def peak_metrics(settings, user, query):
    require(user, MANAGERS)
    where, args = cohort_filters(query)
    with connection(settings) as conn:
        return peak_hours(conn, where, args)

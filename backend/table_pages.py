"""Bounded table transport with database filtering and stable page ordering."""

from datetime import datetime

from backend.core.authorization import authorize, queue_doctor
from backend.core.config import CLINIC_TIMEZONE as TZ
from backend.database import connection
from backend.repositories.queue import (
    DOCTOR_QUEUE_FILTER,
    LIVE_FIELDS,
    LIVE_FILTER,
    LIVE_JOINS,
    PRIORITY_ORDER,
)
from backend.services.metrics import filters
from backend.services.queue_views import decorate_staff_queue_rows


def pattern(value):
    return (
        '%' + value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    )


def metadata(rows, total, page, size):
    return dict(
        rows=rows,
        total=total,
        page=page,
        page_size=size,
        pages=max(1, (total + size - 1) // size),
    )


def queue_page(settings, department, search, status, sort, page, page_size, user):
    authorize(user, 'queue:read')
    doctor_id = queue_doctor(user)
    scope = LIVE_FILTER + DOCTOR_QUEUE_FILTER
    scope_args = (department, department, doctor_id, doctor_id)
    where = (
        scope
        + " AND (%s='all' OR t.status=%s) AND (d.code||'-'||lpad(t.token_no::text,greatest(3,length(t.token_no::text)),'0') ILIKE %s OR d.name ILIKE %s)"
    )
    args = (*scope_args, status, status, pattern(search), pattern(search))

    order = PRIORITY_ORDER + ',t.id' if sort != 'token' else 'd.code,t.token_no,t.id'
    with connection(settings) as conn:
        total = conn.execute(
            'SELECT count(*) AS n' + LIVE_JOINS + ' WHERE ' + where, args
        ).fetchone()['n']
        page = min(page, max(1, (total + page_size - 1) // page_size))
        summary = {
            r['status']: r['n']
            for r in conn.execute(
                'SELECT t.status,count(*) AS n'
                + LIVE_JOINS
                + ' WHERE '
                + scope
                + ' GROUP BY t.status',
                scope_args,
            ).fetchall()
        }
        if doctor_id:
            for status in ('called', 'in_service'):
                summary['my_' + status] = summary.get(status, 0)
        if sort == 'wait':
            # Live estimates require the active queue working set; historical completed rows aren't predicted.
            all_rows = decorate_staff_queue_rows(
                conn,
                conn.execute(
                    LIVE_FIELDS + LIVE_JOINS + ' WHERE ' + where + ' ORDER BY ' + order,
                    args,
                ).fetchall(),
                doctor_id,
            )
            all_rows.sort(
                key=lambda r: (
                    -(r['estimated_wait'] if r['estimated_wait'] is not None else -1)
                )
            )
            rows = all_rows[(page - 1) * page_size : page * page_size]
        else:
            rows = decorate_staff_queue_rows(
                conn,
                conn.execute(
                    LIVE_FIELDS
                    + LIVE_JOINS
                    + ' WHERE '
                    + where
                    + ' ORDER BY '
                    + order
                    + ' LIMIT %s OFFSET %s',
                    args + (page_size, (page - 1) * page_size),
                ).fetchall(),
                doctor_id,
            )
        result = metadata(rows, total, page, page_size)
        result.update(
            summary=summary,
            department_total=sum(
                summary.get(s, 0)
                for s in (
                    'waiting',
                    'called',
                    'in_service',
                    'completed',
                    'cancelled',
                    'no_show',
                )
            ),
            as_of=datetime.now(TZ),
        )
        return result


def audit_page(settings, search, start, end, entity_id, page, page_size, user):
    authorize(user, 'audit:read')
    if start and end:
        filters(start, end)
    joins = ' FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id '
    where = "(a.action ILIKE %s OR coalesce(u.email,'') ILIKE %s OR a.entity_type ILIKE %s) AND (%s::date IS NULL OR (a.created_at AT TIME ZONE 'Asia/Colombo')::date>=%s) AND (%s::date IS NULL OR (a.created_at AT TIME ZONE 'Asia/Colombo')::date<=%s) AND (%s::uuid IS NULL OR a.entity_id=%s)"
    args = (pattern(search),) * 3 + (start, start, end, end, entity_id, entity_id)
    with connection(settings) as conn:
        total = conn.execute(
            'SELECT count(*) AS n' + joins + ' WHERE ' + where, args
        ).fetchone()['n']
        page = min(page, max(1, (total + page_size - 1) // page_size))
        rows = conn.execute(
            'SELECT a.*,u.email'
            + joins
            + ' WHERE '
            + where
            + ' ORDER BY a.created_at DESC,a.id DESC LIMIT %s OFFSET %s',
            args + (page_size, (page - 1) * page_size),
        ).fetchall()
        return metadata(rows, total, page, page_size)


def users_page(settings, search, page, page_size, user):
    authorize(user, 'users:manage')
    args = (pattern(search),)
    with connection(settings) as conn:
        total = conn.execute(
            'SELECT count(*) AS n FROM users WHERE email ILIKE %s', args
        ).fetchone()['n']
        page = min(page, max(1, (total + page_size - 1) // page_size))
        rows = conn.execute(
            'SELECT id,email,role,is_active,display_name FROM users WHERE email ILIKE %s ORDER BY email,id LIMIT %s OFFSET %s',
            args + (page_size, (page - 1) * page_size),
        ).fetchall()
        return metadata(rows, total, page, page_size)


def doctor_options(settings, user):
    authorize(user, 'users:manage')
    with connection(settings) as conn:
        return conn.execute(
            "SELECT id,email,role FROM users u WHERE u.role='doctor' AND u.is_active AND NOT EXISTS(SELECT 1 FROM staff s WHERE s.user_id=u.id) ORDER BY email LIMIT 200"
        ).fetchall()

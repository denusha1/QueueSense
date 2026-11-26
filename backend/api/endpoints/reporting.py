"""HTTP adapter for the existing reporting API."""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Query, Response

from backend.core.authorization import authorize
from backend.api.dependencies import AppSettings, CurrentUser
from backend.schemas.product import (
    CheckIn,
    ImportInput,
    Simulation,
)
from backend.services import reporting

router = APIRouter()


@router.get('/analytics/summary')
def summary(
    settings: AppSettings,
    user: CurrentUser,
    start: date,
    end: date,
    department: uuid.UUID | None = None,
    staff: uuid.UUID | None = None,
    weekday: int | None = Query(None, ge=1, le=7),
    hour_from: int = Query(0, ge=0, le=23),
    hour_to: int = Query(23, ge=0, le=23),
):
    return reporting.summary(
        settings, start, end, department, staff, weekday, hour_from, hour_to, user
    )


@router.post('/simulation/staffing')
def simulation(user: CurrentUser, body: Simulation):
    return reporting.simulation(body, user)


@router.get('/models/performance')
def performance(
    settings: AppSettings,
    user: CurrentUser,
    start: date | None = None,
    end: date | None = None,
    department: uuid.UUID | None = None,
):
    return reporting.performance(settings, start, end, department, user)


@router.post('/predict/wait-time')
def predict(settings: AppSettings, user: CurrentUser, body: CheckIn):
    authorize(user, 'planning:read')
    return reporting.predict(settings, body)


@router.get('/alerts')
def alerts(settings: AppSettings, user: CurrentUser):
    authorize(user, 'alerts:read')
    return reporting.alerts(settings)


@router.post('/alerts/refresh')
def refresh_alerts(settings: AppSettings, user: CurrentUser):
    return reporting.refresh_alerts(settings, user)


@router.post('/alerts/{alert_id}/resolve')
def resolve_alert(settings: AppSettings, user: CurrentUser, alert_id: uuid.UUID):
    return reporting.resolve_alert(settings, alert_id, user)


@router.post('/data/import')
def import_data(settings: AppSettings, user: CurrentUser, body: ImportInput):
    return reporting.import_data(settings, body, user)


@router.get('/reports/export')
def export(
    settings: AppSettings,
    user: CurrentUser,
    start: date,
    end: date,
    format: Literal['csv', 'pdf'] = 'csv',
    report_type: Literal[
        'visits',
        'operational',
        'daily',
        'monthly',
        'doctor',
        'department',
        'waiting',
        'peak_hour',
    ] | None = None,
    department: uuid.UUID | None = None,
    staff: uuid.UUID | None = None,
    weekday: int | None = Query(None, ge=1, le=7),
    hour_from: int = Query(0, ge=0, le=23),
    hour_to: int = Query(23, ge=0, le=23),
):
    content, media = reporting.export(
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
    )
    return Response(
        content,
        media_type=media,
        headers={
            'Content-Disposition': f'attachment; filename="queuesense-{report_type}-{start}-{end}.{format}"',
        },
    )

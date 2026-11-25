"""HTTP adapter for the existing automation API."""

import uuid

from fastapi import APIRouter

from backend import automation
from backend.api.dependencies import AppSettings, CurrentUser

router = APIRouter()


@router.get('/planning/congestion')
def warnings(
    settings: AppSettings, user: CurrentUser, department_id: uuid.UUID | None = None
):
    return automation.warnings(settings, department_id)


@router.get('/appointments/risks')
def risks(settings: AppSettings, user: CurrentUser, day: str):
    return automation.risks(settings, day, user)


@router.get('/notifications')
def staff_feed(settings: AppSettings, user: CurrentUser):
    return automation.staff_feed(settings, user)


@router.post('/notifications/{notification_id}/read')
def staff_read(settings: AppSettings, user: CurrentUser, notification_id: uuid.UUID):
    return automation.staff_read(settings, notification_id, user)


@router.get('/patient/{key}/notifications')
def patient_feed(settings: AppSettings, key: str):
    return automation.patient_feed(settings, key)


@router.get('/self-checkin/{key}/notifications')
def booking_feed(settings: AppSettings, key: str):
    return automation.booking_feed(settings, key)


@router.post('/self-checkin/{key}/confirm')
def confirm(settings: AppSettings, key: str):
    return automation.confirm(settings, key)


@router.post('/patient/{key}/notifications/{notification_id}/read')
def patient_read(settings: AppSettings, key: str, notification_id: uuid.UUID):
    return automation.patient_read(settings, key, notification_id)


@router.post('/self-checkin/{key}/notifications/{notification_id}/read')
def booking_read(settings: AppSettings, key: str, notification_id: uuid.UUID):
    return automation.booking_read(settings, key, notification_id)

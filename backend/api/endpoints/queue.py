"""HTTP adapter for the existing queue API."""

import uuid

from fastapi import APIRouter, Request, Response

from backend.api.dependencies import AppSettings, CurrentUser
from backend.schemas.legacy_responses import PatientStatus, QueueLive
from backend.schemas.product import (
    Availability,
    Change,
    StaffCheckIn,
)
from backend.services import queue

router = APIRouter()


@router.get('/queue/live', response_model=QueueLive, response_model_exclude_unset=True)
def live(settings: AppSettings, user: CurrentUser, department: uuid.UUID | None = None):
    return queue.live(settings, department)


@router.post('/queue/check-in', status_code=201)
def checkin(settings: AppSettings, user: CurrentUser, body: StaffCheckIn):
    return queue.checkin(settings, body, user)


@router.get('/queue/{token_id}/private-link')
def private_link(settings: AppSettings, user: CurrentUser, token_id: uuid.UUID):
    return queue.private_link(settings, token_id, user)


@router.patch('/queue/{token_id}/status')
def change(settings: AppSettings, user: CurrentUser, token_id: uuid.UUID, body: Change):
    return queue.change(settings, token_id, body, user)


@router.post('/staff/{staff_id}/call-next')
def call_next(settings: AppSettings, user: CurrentUser, staff_id: uuid.UUID):
    return queue.call_next(settings, staff_id, user)


@router.patch('/staff/{staff_id}/availability')
def availability(
    settings: AppSettings, user: CurrentUser, staff_id: uuid.UUID, body: Availability
):
    return queue.availability(settings, staff_id, body, user)


@router.post('/queue/{department_id}/close')
def close_session(settings: AppSettings, user: CurrentUser, department_id: uuid.UUID):
    return queue.close_session(settings, department_id, user)


@router.get('/patient/{key}/qr')
def tracking_qr(settings: AppSettings, key: str, origin: str):
    return Response(
        queue.tracking_qr(settings, key, origin), media_type='image/svg+xml'
    )


@router.get('/patient/{key}', response_model=PatientStatus)
def patient(request: Request, settings: AppSettings, key: str):
    return queue.patient(settings, key, request.app.state.public_status_hits)

"""HTTP adapter for the existing arrivals API."""

import uuid
from datetime import date

import psycopg
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from backend import arrivals
from backend.core.authorization import authorize
from backend.api.dependencies import AppSettings, CurrentUser
from backend.api.errors import log_failure
from backend.arrivals import BookingInput, KioskInput, SelfInput, SlotInput
from backend.schemas.legacy_responses import ArrivalInfo, ArrivalReceipt

router = APIRouter()


@router.get('/appointments/slots')
def slots(
    settings: AppSettings,
    user: CurrentUser,
    day: date,
    department: uuid.UUID | None = None,
):
    return arrivals.slots(settings, day, department, user)


@router.post('/appointments/slots', status_code=201)
def create_slot(settings: AppSettings, user: CurrentUser, body: SlotInput):
    return arrivals.create_slot(settings, body, user)


@router.get('/appointments')
def appointments(settings: AppSettings, user: CurrentUser, day: date):
    return arrivals.appointments(settings, day, user)


@router.post('/appointments', status_code=201)
def book(settings: AppSettings, user: CurrentUser, body: BookingInput):
    return arrivals.book(settings, body, user)


@router.post('/appointments/{appointment_id}/cancel')
def cancel(settings: AppSettings, user: CurrentUser, appointment_id: uuid.UUID):
    return arrivals.cancel(settings, appointment_id, user)


@router.get('/checkin/kiosks')
def kiosks(settings: AppSettings, user: CurrentUser):
    return arrivals.kiosks(settings, user)


@router.post('/checkin/kiosks', status_code=201)
def create_kiosk(settings: AppSettings, user: CurrentUser, body: KioskInput):
    return arrivals.create_kiosk(settings, body, user)


@router.post('/checkin/kiosks/{kiosk_id}/revoke')
def revoke(settings: AppSettings, user: CurrentUser, kiosk_id: uuid.UUID):
    return arrivals.revoke(settings, kiosk_id, user)


@router.get('/self-checkin/{key}', response_model=ArrivalInfo)
def info(settings: AppSettings, key: str):
    return arrivals.info(settings, key)


@router.get('/self-checkin/{key}/qr')
def qr(settings: AppSettings, key: str, origin: str):
    return Response(arrivals.qr(settings, key, origin), media_type='image/svg+xml')


@router.post('/self-checkin/{key}', response_model=ArrivalReceipt)
def self_checkin(settings: AppSettings, key: str, body: SelfInput):
    return arrivals.self_checkin(settings, key, body)


@router.get('/queue/events')
async def queue_events(settings: AppSettings, user: CurrentUser, request: Request):
    authorize(user, 'queue:read', 'performance:read')
    return stream(
        request,
        arrivals.events(
            settings,
            'queuesense_queue',
            request.is_disconnected,
            user,
        ),
    )


@router.get('/patient/{key}/events')
def patient_events(settings: AppSettings, key: str, request: Request):
    channel = arrivals.patient_event_channel(settings, key)
    return stream(request, arrivals.events(settings, channel, request.is_disconnected))


def stream(request: Request, events):
    async def deliver():
        try:
            async for event in events:
                yield event
        except psycopg.Error as exc:
            # Headers have already been sent. End the stream so the client can reconnect.
            log_failure(request, exc, 'event_stream_database_failure')

    return StreamingResponse(
        deliver(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no'}
    )

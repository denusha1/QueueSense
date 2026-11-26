"""Read-only clinician directory and schedules."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from backend.core.authorization import authorize
from backend.api.dependencies import AppSettings
from backend.api.v1.dependencies import V1User
from backend.schemas.v1 import (
    ApiError,
    Data,
    Doctor,
    DoctorsQuery,
    Page,
    Schedule,
    ScheduleQuery,
    paged,
)
from backend.services import clinic

router = APIRouter(prefix='/doctors', tags=['v1 doctors'])
NOT_FOUND = {'model': ApiError, 'description': 'Doctor not found'}


@router.get('', response_model=Page[Doctor])
def list_doctors(
    query: Annotated[DoctorsQuery, Query()], settings: AppSettings, user: V1User
):
    authorize(user, 'doctor:read')
    rows, total = clinic.list_doctors(settings, query)
    return paged(rows, total, query)


@router.get('/{doctor_id}', response_model=Data[Doctor], responses={404: NOT_FOUND})
def get_doctor(doctor_id: UUID, settings: AppSettings, user: V1User):
    authorize(user, 'doctor:read')
    return {'data': clinic.get_doctor(settings, doctor_id)}


@router.get(
    '/{doctor_id}/schedule', response_model=Page[Schedule], responses={404: NOT_FOUND}
)
def doctor_schedule(
    doctor_id: UUID,
    query: Annotated[ScheduleQuery, Query()],
    settings: AppSettings,
    user: V1User,
):
    authorize(user, 'doctor:read')
    rows, total = clinic.doctor_schedule(settings, doctor_id, query)
    return paged(rows, total, query)

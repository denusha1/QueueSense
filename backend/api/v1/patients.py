"""Staff operations on the clinic patient registry."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from backend.api.dependencies import AppSettings
from backend.api.v1.contract import PREFIX
from backend.api.v1.dependencies import V1User
from backend.schemas.patients import PatientRegistration
from backend.schemas.v1 import ApiError, Data, Page, Patient, PatientsQuery, paged
from backend.services import patients

router = APIRouter(prefix='/patients', tags=['v1 patients'])


@router.get('', response_model=Page[Patient])
def list_patients(
    query: Annotated[PatientsQuery, Query()], settings: AppSettings, user: V1User
):
    rows, total = patients.list_patients(
        settings,
        user,
        query.external_id,
        query.direction,
        query.page_size,
        query.offset,
    )
    return paged(rows, total, query)


@router.post(
    '',
    status_code=201,
    response_model=Data[Patient],
    responses={200: {'model': Data[Patient], 'description': 'Existing registration'}},
)
def register(
    body: PatientRegistration, response: Response, settings: AppSettings, user: V1User
):
    patient_id, created = patients.register(settings, body.external_id, user)
    if created:
        response.headers['Location'] = f'{PREFIX}/patients/{patient_id}'
    else:
        response.status_code = 200
    return {'data': {'id': patient_id, 'external_id': body.external_id}}


@router.get(
    '/{patient_id}',
    response_model=Data[Patient],
    responses={404: {'model': ApiError, 'description': 'Patient not found'}},
)
def get_patient(patient_id: UUID, settings: AppSettings, user: V1User):
    return {'data': patients.get_patient(settings, user, patient_id)}


@router.patch(
    '/{patient_id}',
    response_model=Data[Patient],
    responses={
        404: {'model': ApiError, 'description': 'Patient not found'},
        409: {
            'model': ApiError,
            'description': 'Clinic identifier is already registered',
        },
    },
)
def update_patient(
    patient_id: UUID, body: PatientRegistration, settings: AppSettings, user: V1User
):
    return {
        'data': patients.update_patient(settings, user, patient_id, body.external_id)
    }

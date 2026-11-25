"""Staff-only patient registration."""

from fastapi import APIRouter, Response

from backend.api.dependencies import AppSettings, CurrentUser
from backend.schemas.patients import PatientReference, PatientRegistration
from backend.services import patients

router = APIRouter()


@router.post('/patients', status_code=201, responses={200: {'model': PatientReference}})
def register_patient(
    settings: AppSettings,
    user: CurrentUser,
    body: PatientRegistration,
    response: Response,
) -> PatientReference:
    patient_id, created = patients.register(settings, body.external_id, user)
    if not created:
        response.status_code = 200
    return PatientReference(id=patient_id)

from fastapi import APIRouter

from backend.api.dependencies import AppSettings
from backend.repositories.health import check_database
from backend.schemas.legacy_responses import HealthStatus

router = APIRouter()


@router.get('/health', response_model=HealthStatus)
def health(settings: AppSettings):
    check_database(settings)
    return {'status': 'ok'}


@router.get('/health/live', response_model=HealthStatus, include_in_schema=False)
def liveness():
    return {'status': 'ok'}

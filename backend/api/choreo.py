"""Read-only origin operation for the QueueSense Choreo API Proxy."""

from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from backend.api.dependencies import AppSettings
from backend.api.errors import INTEGRATION_PREFIX, error_models
from backend.core.choreo import ASSERTION_HEADER
from backend.core.config import CLINIC_TIMEZONE
from backend.core.errors import ServiceError
from backend.database import connection
from backend.repositories import traffic
from backend.schemas.v1 import Data, Input, WaitingTime
from backend.services.metrics import cohort_summary, filters

router = APIRouter(prefix=INTEGRATION_PREFIX, responses=error_models())
MIN_MEASURED_WAITS = 10


class WaitingWeek(Input):
    department_id: UUID
    week_start: date


class WeeklyWaitingTime(BaseModel):
    department_id: UUID
    week_start: date
    suppressed: bool
    metrics: WaitingTime | None


def gateway_department(request: Request) -> UUID:
    return request.app.state.choreo_verifier.authorize(
        request.headers.getlist(ASSERTION_HEADER)
    )


@router.get('/wait-time-summary', response_model=Data[WeeklyWaitingTime])
def wait_time_summary(
    settings: AppSettings,
    query: Annotated[WaitingWeek, Query()],
    allowed_department: Annotated[UUID, Depends(gateway_department)],
):
    if query.department_id != allowed_department:
        raise ServiceError(403, 'This department is not authorized.')
    today = datetime.now(CLINIC_TIMEZONE).date()
    if query.week_start.weekday() != 0 or query.week_start > today - timedelta(days=7):
        raise ServiceError(422, 'Choose the Monday of a completed clinic week.')
    with connection(settings) as conn:
        traffic.consume(conn, 'partner-weekly-read', allowed_department, 30)
    end = query.week_start + timedelta(days=6)
    where, args = filters(query.week_start, end, allowed_department)
    with connection(settings) as conn:
        summary = cohort_summary(conn, where, args)
    suppressed = summary['measured_waits'] < MIN_MEASURED_WAITS
    return {
        'data': WeeklyWaitingTime(
            department_id=allowed_department,
            week_start=query.week_start,
            suppressed=suppressed,
            metrics=None if suppressed else WaitingTime.model_validate(summary),
        )
    }

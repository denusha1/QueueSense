"""HTTP adapter for the existing experience API."""

import uuid
from datetime import date

from fastapi import APIRouter, Path

from backend import experience
from backend.api.dependencies import AppSettings, CurrentUser
from backend.api.traffic import PUBLIC_LINK_TRAFFIC
from backend.experience import Feedback
from backend.schemas.legacy_responses import FeedbackStatus, FeedbackSubmission

router = APIRouter()


@router.get(
    '/patient/{key}/feedback',
    dependencies=PUBLIC_LINK_TRAFFIC,
    response_model=FeedbackStatus,
)
def feedback_status(
    settings: AppSettings, key: str = Path(pattern=r'^[A-Za-z0-9_-]{30,80}$')
):
    return experience.feedback_status(settings, key)


@router.post(
    '/patient/{key}/feedback',
    dependencies=PUBLIC_LINK_TRAFFIC,
    status_code=201,
    response_model=FeedbackSubmission,
)
def submit_feedback(
    settings: AppSettings,
    body: Feedback,
    key: str = Path(pattern=r'^[A-Za-z0-9_-]{30,80}$'),
):
    return experience.submit_feedback(settings, body, key)


@router.get('/feedback/summary')
def summary(
    settings: AppSettings,
    user: CurrentUser,
    start: date,
    end: date,
    department: uuid.UUID | None = None,
):
    return experience.summary(settings, start, end, department, user)


@router.get('/health/services')
def services(settings: AppSettings, user: CurrentUser):
    return experience.services(settings, user)

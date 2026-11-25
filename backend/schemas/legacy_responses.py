"""Response projections for browser-facing JSON endpoints."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from backend.schemas.product import QueueStatus


class HealthStatus(BaseModel):
    status: Literal['ok']


class DemoStatus(BaseModel):
    enabled: bool


class Acknowledgement(BaseModel):
    ok: bool


class PredictionContribution(BaseModel):
    feature: str
    input: str | int | float | None
    impact: float
    direction: str


class PredictionExplanation(BaseModel):
    method: str
    baseline: float
    model_output: float
    capacity_floor: float
    contributions: list[PredictionContribution]
    note: str


class PatientStatus(BaseModel):
    token: str
    department: str
    status: QueueStatus
    priority_class: Literal['standard', 'expedited']
    position: int | None
    patients_ahead: int | None
    estimated_wait: float | None
    prediction_source: str | None
    explanation: PredictionExplanation | None
    initial_prediction: float | None
    actual_wait: float | None
    prediction_error: float | None
    notice: str


class QueueLiveToken(BaseModel):
    id: UUID
    department_id: UUID
    staff_id: UUID | None
    token_no: int
    status: QueueStatus
    priority_class: Literal['standard', 'expedited']
    priority_reason: str
    initial_wait_minutes: float | None
    initial_prediction_version: str | None
    check_in_at: datetime
    called_at: datetime | None
    service_start_at: datetime | None
    completed_at: datetime | None
    code: str
    department: str
    clinician: str | None
    position: int | None
    patients_ahead: int | None
    estimated_wait: float | None
    prediction_source: str | None = None
    prediction_notice: str | None = None
    actual_wait: float | None
    prediction_error: float | None


class QueueLive(BaseModel):
    tokens: list[QueueLiveToken]
    as_of: datetime
    limit: int


class QueuePage(BaseModel):
    rows: list[QueueLiveToken]
    as_of: datetime
    total: int
    page: int
    page_size: int
    pages: int
    summary: dict[str, int]
    department_total: int


class ArrivalInfo(BaseModel):
    kind: Literal['appointment', 'walkin']
    department: str
    reference: str | None
    starts_at: datetime | None
    status: Literal['open', 'booked', 'checked_in', 'cancelled']
    active: bool


class ArrivalReceipt(BaseModel):
    patient_key: str


class FeedbackSubmission(BaseModel):
    submitted: bool


class FeedbackStatus(FeedbackSubmission):
    eligible: bool

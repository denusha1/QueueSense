"""Validated requests for queue, clinic, and reporting operations."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.schemas.text import SingleLine

QueueStatus = Literal[
    'waiting', 'called', 'in_service', 'completed', 'cancelled', 'no_show'
]


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CheckIn(Input):
    department_id: uuid.UUID
    priority_class: Literal['standard', 'expedited'] = 'standard'
    priority_reason: SingleLine = Field(default='', max_length=160)
    service_type: Literal[
        'general_consultation',
        'follow_up',
        'document_review',
        'accessible_consultation',
    ] = 'general_consultation'
    required_language: Literal['en', 'ta', 'si'] | None = None
    preferred_staff_id: uuid.UUID | None = None
    continuity_required: bool = False

    @model_validator(mode='after')
    def continuity(self):
        self.priority_reason = self.priority_reason.strip()
        if self.priority_class == 'expedited' and len(self.priority_reason) < 3:
            raise ValueError(
                'Record a clinic policy reference or staff authorization for expedited priority.'
            )
        if self.continuity_required and self.preferred_staff_id is None:
            raise ValueError('Choose a doctor when continuity is required.')
        return self


class StaffCheckIn(CheckIn):
    patient_id: uuid.UUID | None = None


class Change(Input):
    status: Literal['called', 'in_service', 'completed', 'cancelled', 'no_show']
    staff_id: uuid.UUID | None = None


class Availability(Input):
    status: Literal['available', 'break', 'offline']


class Simulation(Input):
    queue: int = Field(ge=0, le=10000)
    staff: int = Field(ge=1, le=100)
    arrivals_per_hour: float = Field(ge=0, le=10000, allow_inf_nan=False)
    service_minutes: float = Field(gt=0, le=240, allow_inf_nan=False)


class DepartmentInput(Input):
    code: str = Field(pattern='^[A-Z]{2,8}$')
    name: SingleLine = Field(min_length=2, max_length=80)
    location: SingleLine = Field(min_length=1, max_length=100)
    queue_threshold: int = Field(ge=1, le=1000)


class UserInput(Input):
    email: SingleLine = Field(pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$', max_length=254)
    password: str = Field(min_length=12, max_length=128)
    role: Literal['admin', 'manager', 'doctor', 'reception']


class UserUpdate(Input):
    role: Literal['admin', 'manager', 'doctor', 'reception']
    is_active: bool


class StaffInput(Input):
    department_id: uuid.UUID
    display_name: SingleLine = Field(min_length=2, max_length=80)
    user_id: uuid.UUID | None = None


class ScheduleInput(Input):
    start_at: datetime
    end_at: datetime


class ImportInput(Input):
    csv_text: str = Field(max_length=2_000_000)
    dry_run: bool = True

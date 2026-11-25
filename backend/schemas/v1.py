"""Stable public shapes for the private versioned staff API."""

from datetime import date, datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.auth import Session as Session
from backend.schemas.errors import ApiError as ApiError
from backend.schemas.product import Input, QueueStatus

T = TypeVar('T')

EventType = Literal[
    'check_in', 'called', 'service_start', 'completed', 'cancelled', 'no_show'
]
Direction = Literal['asc', 'desc']


class Data(BaseModel, Generic[T]):
    data: T


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class Page(Data[list[T]], Generic[T]):
    pagination: Pagination


class Paging(Input):
    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=25, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def paged(rows, total: int, paging: Paging):
    return {
        'data': rows,
        'pagination': {
            'page': paging.page,
            'page_size': paging.page_size,
            'total': total,
            'pages': (total + paging.page_size - 1) // paging.page_size,
        },
    }


class Patient(BaseModel):
    id: UUID
    external_id: str


class PatientsQuery(Paging):
    external_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]*$',
    )
    direction: Direction = 'asc'


class QueueQuery(Paging):
    department_id: UUID | None = None
    staff_id: UUID | None = None
    status: QueueStatus | None = None
    day: date | None = None
    sort: Literal['priority', 'arrival', 'token'] = 'priority'
    direction: Direction = 'asc'


class QueueToken(BaseModel):
    id: UUID
    department_id: UUID
    staff_id: UUID | None
    token_no: int
    status: QueueStatus
    priority_class: Literal['standard', 'expedited']
    check_in_at: datetime
    called_at: datetime | None
    service_start_at: datetime | None
    completed_at: datetime | None
    ended_at: datetime | None


class QueueEvent(BaseModel):
    id: UUID
    event_type: EventType
    event_time: datetime
    staff_id: UUID | None


class DoctorsQuery(Paging):
    department_id: UUID | None = None
    active: bool | None = None
    direction: Direction = 'asc'


class Doctor(BaseModel):
    id: UUID
    department_id: UUID
    display_name: str
    is_active: bool
    availability: Literal['available', 'busy', 'break', 'offline']


class ScheduleQuery(Paging):
    start: date
    end: date
    status: Literal['scheduled', 'cancelled'] | None = None
    direction: Direction = 'asc'


class Schedule(BaseModel):
    id: UUID
    staff_id: UUID
    service_date: date
    start_at: datetime
    end_at: datetime
    status: Literal['scheduled', 'cancelled']


class AnalyticsQuery(Input):
    start: date
    end: date
    department_id: UUID | None = None
    staff_id: UUID | None = None
    weekday: int | None = Field(default=None, ge=1, le=7)
    hour_from: int = Field(default=0, ge=0, le=23)
    hour_to: int = Field(default=23, ge=0, le=23)


class WaitingTime(BaseModel):
    measured_waits: int
    average_wait: float | None
    median_wait: float | None
    p90_wait: float | None


class PeakHour(BaseModel):
    weekday: int
    hour: int
    arrivals: int
    wait: float | None


class QueuePerformance(BaseModel):
    arrivals: int
    completed: int
    waiting: int
    cancelled: int
    no_shows: int
    average_service: float | None
    cancellation_rate: float | None
    no_show_rate: float | None

"""HTTP adapter for the existing clinic API."""

import uuid
from datetime import date

from fastapi import APIRouter, Query

from backend.core.authorization import authorize
from backend.api.dependencies import AppSettings, CurrentUser
from backend.schemas.product import (
    DepartmentInput,
    ScheduleInput,
    StaffInput,
    UserInput,
    UserUpdate,
)
from backend.schemas.text import SingleLine
from backend.services import clinic

router = APIRouter()


@router.get('/departments')
def departments(settings: AppSettings, user: CurrentUser):
    authorize(user, 'department:read')
    return clinic.departments(settings)


@router.get('/staff')
def staff(settings: AppSettings, user: CurrentUser):
    return clinic.staff(settings, user)


@router.get('/admin/users')
def users(settings: AppSettings, user: CurrentUser):
    return clinic.users(settings, user)


@router.post('/admin/users', status_code=201)
def create_user(settings: AppSettings, user: CurrentUser, body: UserInput):
    return clinic.create_user(settings, body, user)


@router.patch('/admin/users/{user_id}')
def update_user(
    settings: AppSettings, user: CurrentUser, user_id: uuid.UUID, body: UserUpdate
):
    return clinic.update_user(settings, user_id, body, user)


@router.post('/admin/departments', status_code=201)
def add_department(settings: AppSettings, user: CurrentUser, body: DepartmentInput):
    return clinic.add_department(settings, body, user)


@router.patch('/admin/departments/{department_id}')
def update_department(
    settings: AppSettings,
    user: CurrentUser,
    department_id: uuid.UUID,
    body: DepartmentInput,
):
    return clinic.update_department(settings, department_id, body, user)


@router.post('/admin/staff', status_code=201)
def add_staff(settings: AppSettings, user: CurrentUser, body: StaffInput):
    return clinic.add_staff(settings, body, user)


@router.get('/schedules')
def schedules(settings: AppSettings, user: CurrentUser, start: date, end: date):
    authorize(user, 'doctor:read')
    return clinic.schedules(settings, start, end)


@router.post('/admin/staff/{staff_id}/schedule')
def schedule(
    settings: AppSettings, user: CurrentUser, staff_id: uuid.UUID, body: ScheduleInput
):
    return clinic.schedule(settings, staff_id, body, user)


@router.get('/audit')
def audit_log(
    settings: AppSettings,
    user: CurrentUser,
    search: SingleLine = Query('', max_length=100),
    start: date | None = None,
    end: date | None = None,
    entity_id: uuid.UUID | None = None,
    offset: int = Query(0, ge=0, le=1000000),
):
    return clinic.audit_log(settings, search, start, end, entity_id, offset, user)

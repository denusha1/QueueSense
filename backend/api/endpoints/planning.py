"""HTTP adapter for the existing planning API."""

import uuid
from datetime import date

from fastapi import APIRouter, Path, Query

from backend import planning
from backend.api.dependencies import AppSettings, CurrentUser
from backend.planning import Comparison, DoctorRequest, Profile

router = APIRouter()


@router.post('/planning/doctors')
def doctors(settings: AppSettings, user: CurrentUser, body: DoctorRequest):
    return planning.doctors(settings, body)


@router.get('/patient/{key}/doctors')
def patient_doctors(
    settings: AppSettings, key: str = Path(pattern=r'^[A-Za-z0-9_-]{30,80}$')
):
    return planning.patient_doctors(settings, key)


@router.get('/planning/balance')
def balance(settings: AppSettings, user: CurrentUser, department_id: uuid.UUID):
    return planning.balance(settings, department_id)


@router.get('/planning/forecast')
def demand(
    settings: AppSettings,
    user: CurrentUser,
    department_id: uuid.UUID,
    day: date,
    weeks: int = Query(8, ge=4, le=26),
    target_utilization: float = Query(0.8, ge=0.5, le=0.95),
    clearance_minutes: int = Query(60, ge=15, le=240),
):
    return planning.demand(
        settings, department_id, day, weeks, target_utilization, clearance_minutes, user
    )


@router.post('/planning/simulate')
def what_if(user: CurrentUser, body: Comparison):
    return planning.what_if(body, user)


@router.patch('/admin/staff/{staff_id}/profile')
def profile(
    settings: AppSettings, user: CurrentUser, staff_id: uuid.UUID, body: Profile
):
    return planning.profile(settings, staff_id, body, user)

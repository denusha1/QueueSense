"""Compose the existing unversioned API without changing its public URLs."""

from fastapi import APIRouter

from backend.api.endpoints import (
    accounts,
    arrivals,
    auth,
    automation,
    clinic,
    delivery,
    experience,
    health,
    patients,
    planning,
    queue,
    reporting,
    table_pages,
)
from backend.api.errors import error_models
from backend.api.v1.router import router as v1_router

router = APIRouter(responses=error_models(legacy=True))
router.include_router(auth.router)
router.include_router(health.router)
router.include_router(accounts.router)
router.include_router(delivery.router)
router.include_router(table_pages.router)
router.include_router(arrivals.router)
router.include_router(queue.router)
router.include_router(patients.router)
router.include_router(clinic.router)
router.include_router(reporting.router)
router.include_router(experience.router)
router.include_router(planning.router)
router.include_router(automation.router)
router.include_router(v1_router)

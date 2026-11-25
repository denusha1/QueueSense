"""Private v1 staff API. This contract is separate from future external integrations."""

from fastapi import APIRouter

from backend.api.v1 import analytics, auth, doctors, patients, queue
from backend.api.v1.contract import COMMON_ERRORS, PREFIX

router = APIRouter(prefix=PREFIX, responses=COMMON_ERRORS)
for resource in (auth, patients, queue, doctors, analytics):
    router.include_router(resource.router)

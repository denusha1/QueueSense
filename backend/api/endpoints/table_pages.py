"""HTTP adapter for the existing table pages API."""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Query

from backend import table_pages
from backend.api.dependencies import AppSettings, CurrentUser
from backend.schemas.legacy_responses import QueuePage
from backend.schemas.text import SingleLine

router = APIRouter()


@router.get('/queue/page', response_model=QueuePage, response_model_exclude_unset=True)
def queue_page(
    settings: AppSettings,
    user: CurrentUser,
    department: uuid.UUID | None = None,
    search: SingleLine = Query('', max_length=100),
    status: Literal[
        'all', 'waiting', 'called', 'in_service', 'completed', 'cancelled', 'no_show'
    ] = 'all',
    sort: Literal['arrival', 'token', 'wait'] = 'arrival',
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(10, ge=1, le=50),
):
    return table_pages.queue_page(
        settings, department, search, status, sort, page, page_size, user
    )


@router.get('/audit/page')
def audit_page(
    settings: AppSettings,
    user: CurrentUser,
    search: SingleLine = Query('', max_length=100),
    start: date | None = None,
    end: date | None = None,
    entity_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(10, ge=1, le=50),
):
    return table_pages.audit_page(
        settings, search, start, end, entity_id, page, page_size, user
    )


@router.get('/admin/users/page')
def users_page(
    settings: AppSettings,
    user: CurrentUser,
    search: SingleLine = Query('', max_length=100),
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(10, ge=1, le=50),
):
    return table_pages.users_page(settings, search, page, page_size, user)


@router.get('/admin/doctor-options')
def doctor_options(settings: AppSettings, user: CurrentUser):
    return table_pages.doctor_options(settings, user)

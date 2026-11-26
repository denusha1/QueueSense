"""Token resources backed by the existing check-in and transition use cases."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from backend.api.dependencies import AppSettings
from backend.api.v1.contract import PREFIX
from backend.api.v1.dependencies import V1User
from backend.schemas.product import Change, StaffCheckIn
from backend.schemas.v1 import (
    ApiError,
    Data,
    Page,
    Paging,
    QueueEvent,
    QueueQuery,
    QueueToken,
    paged,
)
from backend.services import queue

router = APIRouter(prefix='/queue', tags=['v1 queue'])
NOT_FOUND = {'model': ApiError, 'description': 'Referenced resource not found'}
CONFLICT = {
    'model': ApiError,
    'description': 'Queue state conflicts with the operation',
}


@router.get('', response_model=Page[QueueToken])
def list_tokens(
    query: Annotated[QueueQuery, Query()], settings: AppSettings, user: V1User
):
    rows, total = queue.list_records(settings, query, user)
    return paged(rows, total, query)


@router.post(
    '',
    status_code=201,
    response_model=Data[QueueToken],
    responses={404: NOT_FOUND, 409: CONFLICT},
)
def create_token(
    body: StaffCheckIn, response: Response, settings: AppSettings, user: V1User
):
    token = queue.checkin(settings, body, user)
    response.headers['Location'] = f'{PREFIX}/queue/{token["id"]}'
    return {'data': token}


@router.get('/{token_id}', response_model=Data[QueueToken], responses={404: NOT_FOUND})
def get_token(token_id: UUID, settings: AppSettings, user: V1User):
    return {'data': queue.get_record(settings, token_id, user)}


@router.patch(
    '/{token_id}',
    response_model=Data[QueueToken],
    responses={404: NOT_FOUND, 409: CONFLICT},
)
def update_token(token_id: UUID, body: Change, settings: AppSettings, user: V1User):
    return {'data': queue.change(settings, token_id, body, user)}


@router.get(
    '/{token_id}/history', response_model=Page[QueueEvent], responses={404: NOT_FOUND}
)
def token_history(
    token_id: UUID,
    query: Annotated[Paging, Query()],
    settings: AppSettings,
    user: V1User,
):
    rows, total = queue.history(settings, token_id, query.page_size, query.offset, user)
    return paged(rows, total, query)

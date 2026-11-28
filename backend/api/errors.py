"""Translate backend failures into one safe API error envelope."""

import logging
from collections.abc import Mapping
from http import HTTPStatus

import psycopg
from psycopg_pool import TooManyRequests
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from backend.api.request_ids import REQUEST_ID_HEADER
from backend.core.errors import ServiceError
from backend.core.logging import log_event
from backend.schemas.errors import ApiError, LegacyApiError

LOG = logging.getLogger('queuesense.api')
V1_PREFIX = '/api/v1'
INTEGRATION_PREFIX = '/api/integrations/v1'
DATABASE_FAILURE = 'The database service is temporarily unavailable. Please try again.'
TIMEOUT_MESSAGE = 'The operation exceeded its database time limit. Please try again.'
ERROR_CODES = {
    400: 'bad_request',
    401: 'unauthenticated',
    403: 'forbidden',
    404: 'not_found',
    405: 'method_not_allowed',
    409: 'conflict',
    410: 'gone',
    413: 'request_too_large',
    422: 'validation_error',
    429: 'rate_limited',
    500: 'internal_error',
    503: 'service_unavailable',
    504: 'timeout',
}
COMMON_RESPONSES = {
    400: 'Malformed request',
    401: 'Valid staff session required',
    403: 'Origin or operation forbidden',
    422: 'Invalid request',
    429: 'Request limit reached',
    500: 'Unexpected server failure',
    503: 'Backend temporarily unavailable',
    504: 'Operation timed out',
}


def error_models(*, legacy: bool = False):
    model = LegacyApiError if legacy else ApiError
    return {
        status: {
            'model': model,
            'description': description,
            'headers': {
                REQUEST_ID_HEADER: {'schema': {'type': 'string', 'format': 'uuid'}},
                **(
                    {'Retry-After': {'schema': {'type': 'integer', 'minimum': 1}}}
                    if status == 429
                    else {}
                ),
            },
        }
        for status, description in COMMON_RESPONSES.items()
    }


def error_response(
    request: Request,
    status: int,
    message: str,
    *,
    headers: Mapping[str, str] | None = None,
    invalid_fields: list[dict] | None = None,
):
    request_id = request.state.request_id
    details = [
        {'field': '.'.join(map(str, issue['loc'])), 'code': issue['type']}
        for issue in invalid_fields or ()
    ]
    common = {
        'success': False,
        'error': {
            'code': ERROR_CODES.get(status, 'request_failed'),
            'message': message,
            'details': details,
        },
        'request_id': request_id,
    }
    path = request.scope['path']
    if any(
        path == base or path.startswith(base + '/')
        for base in (V1_PREFIX, INTEGRATION_PREFIX)
    ):
        payload = ApiError.model_validate(common)
    else:
        payload = LegacyApiError.model_validate(
            {
                **common,
                'detail': message if invalid_fields is None else invalid_fields,
            }
        )
    return JSONResponse(
        payload.model_dump(mode='json'),
        status_code=status,
        headers={
            **(headers or {}),
            'Cache-Control': 'no-store',
            REQUEST_ID_HEADER: request_id,
        },
    )


async def http_error(request: Request, exc: HTTPException):
    # Framework details may include exception text. Domain messages use ServiceError.
    try:
        message = HTTPStatus(exc.status_code).phrase
    except ValueError:
        message = 'Request failed.'
    return error_response(
        request,
        exc.status_code,
        message,
        headers=exc.headers,
    )


async def service_error(request: Request, exc: ServiceError):
    if exc.status_code >= 500:
        log_failure(request, exc, 'application_service_failure')
    return error_response(request, exc.status_code, exc.detail, headers=exc.headers)


async def validation_error(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    if any(issue['type'] == 'json_invalid' for issue in errors):
        return error_response(request, 400, 'Request body contains malformed JSON.')
    invalid_fields = []
    for issue in errors[:25]:
        # Unknown fields and nested keys can be user-controlled.
        loc = issue['loc'][:-1] if issue['type'] == 'extra_forbidden' else issue['loc']
        invalid_fields.append(
            {
                'loc': loc[:2],
                'type': issue['type'],
                'msg': 'Invalid field value.',
            }
        )
    return error_response(
        request,
        422,
        'Request validation failed.',
        invalid_fields=invalid_fields,
    )


def log_failure(request: Request, exc: Exception, event: str) -> None:
    route = getattr(request.scope.get('route'), 'path', '<unmatched>')
    log_event(
        LOG,
        logging.ERROR,
        event,
        route=route,
        method=request.method,
        request_id=request.state.request_id,
        error_type=type(exc).__name__,
    )


async def database_error(request: Request, exc: psycopg.Error):
    if isinstance(exc, (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable)):
        log_failure(request, exc, 'database_timeout')
        return error_response(request, 504, TIMEOUT_MESSAGE)
    if isinstance(
        exc,
        (
            psycopg.errors.UniqueViolation,
            psycopg.errors.ForeignKeyViolation,
            psycopg.errors.ExclusionViolation,
        ),
    ):
        log_failure(request, exc, 'database_conflict')
        return error_response(
            request, 409, 'The operation conflicts with existing data.'
        )
    log_failure(request, exc, 'database_unavailable')
    return error_response(request, 503, DATABASE_FAILURE)


def unexpected_error(request: Request, exc: Exception):
    log_failure(request, exc, 'unexpected_api_failure')
    return error_response(request, 500, 'An unexpected server error occurred.')


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(ServiceError, service_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(psycopg.Error, database_error)
    app.add_exception_handler(TooManyRequests, database_error)

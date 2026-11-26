"""Authenticate private v1 routes with a JWT bearer or the staff session cookie."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from backend.api.dependencies import AppSettings
from backend.core.errors import ServiceError
from backend.core.jwt import INVALID_TOKEN
from backend.core.security import COOKIE
from backend.services.auth import StaffSession, resolve_session
from backend.services.traffic import enforce_staff

cookie_scheme = APIKeyCookie(
    name=COOKIE,
    scheme_name='QueueSenseStaffSession',
    description='HttpOnly staff access cookie.',
    auto_error=False,
)
bearer_scheme = HTTPBearer(
    scheme_name='QueueSenseAccessJWT', bearerFormat='JWT', auto_error=False
)
SessionCookie = Annotated[str | None, Depends(cookie_scheme)]
BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
]


def current_staff(
    request: Request,
    settings: AppSettings,
    token: SessionCookie,
    bearer: BearerCredentials,
) -> StaffSession:
    authorization = request.headers.getlist('authorization')
    if authorization:
        if not settings.jwt or len(authorization) != 1 or not bearer:
            raise ServiceError(
                401, INVALID_TOKEN, headers={'WWW-Authenticate': 'Bearer'}
            )
        token = bearer.credentials
    try:
        user = resolve_session(settings, token or '')
    except ServiceError as exc:
        if exc.status_code == 401 and settings.jwt:
            raise ServiceError(
                401, exc.detail, headers={'WWW-Authenticate': 'Bearer'}
            ) from None
        raise

    enforce_staff(settings, request.method, request.url.path, user)
    return user


V1User = Annotated[StaffSession, Depends(current_staff)]

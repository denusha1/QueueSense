"""Authenticate staff clients and rotate the refresh cookie."""

from typing import Literal

from fastapi import APIRouter, Request, Response

from backend.api.cookies import clear_session_cookie
from backend.api.dependencies import AppSettings
from backend.api.endpoints.auth import renew, sign_in
from backend.api.v1.dependencies import BearerCredentials
from backend.core.security import COOKIE, REFRESH_COOKIE
from backend.schemas.auth import Credentials
from backend.schemas.v1 import ApiError, Data, Session
from backend.services.auth import SessionTokens, StaffSession, end_session

router = APIRouter(prefix='/auth', tags=['v1 authentication'])


class AuthResult(Data[Session]):
    access_token: str | None = None
    token_type: Literal['Bearer'] | None = None


def result(tokens: SessionTokens, user: StaffSession):
    payload = {'data': user}
    if tokens.refresh:
        payload.update(access_token=tokens.access, token_type='Bearer')
    return payload


@router.post(
    '/login',
    response_model=AuthResult,
    response_model_exclude_none=True,
    responses={429: {'model': ApiError, 'description': 'Too many sign-in attempts'}},
)
def login(
    body: Credentials,
    request: Request,
    response: Response,
    settings: AppSettings,
):
    return result(
        *sign_in(
            settings,
            request,
            response,
            body.email,
            body.role,
            body.password,
            otp=body.otp,
        )
    )


@router.post('/refresh', response_model=AuthResult, response_model_exclude_none=True)
def refresh(request: Request, response: Response, settings: AppSettings):
    return result(*renew(request, response, settings))


@router.post('/logout', status_code=204, response_class=Response)
def logout(
    request: Request,
    response: Response,
    settings: AppSettings,
    bearer: BearerCredentials,
):
    access = (
        bearer.credentials if settings.jwt and bearer else request.cookies.get(COOKIE)
    )
    end_session(settings, access, request.cookies.get(REFRESH_COOKIE))
    clear_session_cookie(response, settings)

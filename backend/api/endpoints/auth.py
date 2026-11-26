"""Browser sign-in, workspace and sign-out routes."""

from fastapi import APIRouter, Request, Response

from backend.core.authorization import authorize
from backend.api.cookies import clear_session_cookie, set_session_cookies
from backend.api.dependencies import AppSettings, CurrentUser
from backend.core.errors import ServiceError
from backend.core.security import COOKIE, REFRESH_COOKIE, Role
from backend.schemas.auth import (
    WORKSPACES,
    Credentials,
    DemoRequest,
    Session,
    WorkspaceResponse,
)
from backend.schemas.legacy_responses import Acknowledgement, DemoStatus
from backend.services import auth

router = APIRouter()


def sign_in(
    settings, request, response, email, role, password='', *, demo=False, otp=None
):
    tokens, user = auth.authenticate(
        settings,
        email,
        role,
        request.client.host if request.client else 'unknown',
        (request.cookies.get(REFRESH_COOKIE) or request.cookies.get(COOKIE))
        if settings.jwt
        else request.cookies.get(COOKIE),
        request.headers.get('user-agent', 'Browser session'),
        password,
        demo=demo,
        otp=otp,
    )
    set_session_cookies(response, settings, tokens, user)
    return tokens, user


@router.post('/auth/login', response_model=Session, response_model_exclude_none=True)
def login(
    body: Credentials, request: Request, response: Response, settings: AppSettings
):
    return sign_in(
        settings, request, response, body.email, body.role, body.password, otp=body.otp
    )[1]


@router.get('/auth/demo', response_model=DemoStatus)
def demo_status(settings: AppSettings):
    return {'enabled': settings.demo_enabled}


@router.post('/auth/demo', response_model=Session, response_model_exclude_none=True)
def demo_login(
    body: DemoRequest, request: Request, response: Response, settings: AppSettings
):
    if not settings.demo_enabled:
        raise ServiceError(404, 'Demo sign-in is unavailable.')
    return sign_in(
        settings,
        request,
        response,
        f'{body.role}@demo.queuesense.test',
        body.role,
        demo=True,
    )[1]


@router.get('/auth/me', response_model=Session, response_model_exclude_none=True)
def me(user: CurrentUser):
    authorize(user, 'account:self')
    return user


@router.get(
    '/auth/workspace/{role}',
    response_model=WorkspaceResponse,
    response_model_exclude_none=True,
)
def workspace(role: Role, user: CurrentUser):
    authorize(user, 'account:self')
    if user['role'] != role:
        raise ServiceError(403, 'You do not have access to this workspace.')
    return {'user': user, 'workspace': WORKSPACES[role]}


@router.post('/auth/logout', response_model=Acknowledgement)
def logout(request: Request, response: Response, settings: AppSettings):
    auth.end_session(
        settings, request.cookies.get(COOKIE), request.cookies.get(REFRESH_COOKIE)
    )
    clear_session_cookie(response, settings)
    return {'ok': True}


def renew(
    request: Request,
    response: Response,
    settings: AppSettings,
):
    name = REFRESH_COOKIE if settings.jwt else COOKIE
    tokens, user = auth.refresh_session(settings, request.cookies.get(name, ''))
    set_session_cookies(response, settings, tokens, user)
    return tokens, user


@router.post('/auth/refresh', response_model=Session, response_model_exclude_none=True)
def refresh(request: Request, response: Response, settings: AppSettings):
    return renew(request, response, settings)[1]

"""HTTP adapter for the existing accounts API."""

import uuid

from fastapi import APIRouter, Request, Response

from backend import accounts
from backend.accounts import Challenge, Email, Password, Profile, Reset
from backend.api.cookies import clear_session_cookie, set_session_cookies
from backend.api.dependencies import AppSettings, CurrentUser

router = APIRouter()


@router.get('/auth/profile')
def profile(settings: AppSettings, user: CurrentUser):
    return accounts.profile(settings, user)


@router.post('/auth/profile')
def save_profile(settings: AppSettings, user: CurrentUser, body: Profile):
    return accounts.save_profile(settings, body, user)


@router.get('/auth/sessions')
def sessions(settings: AppSettings, user: CurrentUser):
    return accounts.sessions(settings, user)


@router.post('/auth/sessions/{session_id}/revoke')
def revoke(
    settings: AppSettings,
    user: CurrentUser,
    session_id: uuid.UUID,
    response: Response,
):
    result = accounts.revoke(settings, session_id, user)
    if result['current']:
        clear_session_cookie(response, settings)
    return result


@router.post('/auth/password')
def password(
    settings: AppSettings,
    user: CurrentUser,
    body: Password,
    request: Request,
    response: Response,
):
    tokens, session = accounts.password(
        settings, body, request.headers.get('user-agent', 'Browser session'), user
    )
    set_session_cookies(response, settings, tokens, session)
    return {'ok': True}


@router.post('/auth/mfa/setup')
def setup(settings: AppSettings, user: CurrentUser, body: Challenge):
    return accounts.setup(settings, body, user)


@router.post('/auth/mfa/confirm')
def confirm(settings: AppSettings, user: CurrentUser, body: Challenge):
    return accounts.confirm(settings, body, user)


@router.post('/auth/mfa/disable')
def disable(settings: AppSettings, user: CurrentUser, body: Challenge):
    return accounts.disable(settings, body, user)


@router.post('/auth/recovery/request')
def request_recovery(settings: AppSettings, body: Email, request: Request):
    return accounts.request_recovery(
        settings, body, request.client.host if request.client else 'unknown'
    )


@router.post('/auth/recovery/reset')
def reset(settings: AppSettings, body: Reset, request: Request):
    return accounts.reset(
        settings, body, request.client.host if request.client else 'unknown'
    )


@router.post('/auth/recovery/admin/{user_id}')
def admin_recovery(
    settings: AppSettings, user: CurrentUser, user_id: uuid.UUID, body: Challenge
):
    return accounts.admin_recovery(settings, user_id, body, user)

"""Write the browser's HttpOnly session credentials."""

from datetime import datetime, timezone
from math import ceil

from fastapi import Response

from backend.core.config import Settings
from backend.core.security import COOKIE, REFRESH_COOKIE
from backend.services.auth import SessionTokens, StaffSession


def max_age(expires_at: datetime) -> int:
    return max(0, ceil((expires_at - datetime.now(timezone.utc)).total_seconds()))


def set_session_cookies(
    response: Response,
    settings: Settings,
    tokens: SessionTokens,
    user: StaffSession,
) -> None:
    response.set_cookie(
        COOKIE,
        tokens.access,
        httponly=True,
        secure=settings.secure_cookie,
        samesite='lax',
        max_age=max_age(user.get('access_expires_at', user['expires_at'])),
        path='/',
    )
    if tokens.refresh:
        response.set_cookie(
            REFRESH_COOKIE,
            tokens.refresh,
            httponly=True,
            secure=settings.secure_cookie,
            samesite='strict',
            max_age=max_age(user['expires_at']),
            path='/',
        )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        COOKIE,
        httponly=True,
        secure=settings.secure_cookie,
        samesite='lax',
        path='/',
    )
    response.delete_cookie(
        REFRESH_COOKIE,
        httponly=True,
        secure=settings.secure_cookie,
        samesite='strict',
        path='/',
    )

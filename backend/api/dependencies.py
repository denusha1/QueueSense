"""Explicit per-request dependencies for settings and authenticated staff."""

from typing import Annotated

from fastapi import Depends, Request

from backend.core.config import Settings
from backend.core.security import COOKIE
from backend.services.auth import StaffSession, resolve_session
from backend.services.traffic import enforce_staff


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


AppSettings = Annotated[Settings, Depends(get_settings)]


def current_user(request: Request, settings: AppSettings) -> StaffSession:
    user = resolve_session(settings, request.cookies.get(COOKIE, ''))
    enforce_staff(settings, request.method, request.url.path, user)
    return user


CurrentUser = Annotated[StaffSession, Depends(current_user)]

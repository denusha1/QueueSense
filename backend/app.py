"""FastAPI entry point used by Uvicorn, the container, and existing callers."""

from fastapi import FastAPI

from backend.api.choreo import router as choreo_router
from backend.api.errors import register_exception_handlers
from backend.api.middleware import headers_and_origin
from backend.api.router import router
from backend.automation import lifespan
from backend.core.choreo import ChoreoVerifier
from backend.core.config import Settings as Settings
from backend.core.rate_limit import SlidingWindowLimiter
from backend.core.security import COOKIE as COOKIE
from backend.core.security import HASHER as HASHER
from backend.core.security import digest as digest
from backend.database import connection as connection
from backend.schemas.auth import WORKSPACES as WORKSPACES
from backend.schemas.auth import Credentials as Credentials


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings.from_env()
    docs = (
        {'docs_url': None, 'redoc_url': None, 'openapi_url': None}
        if settings.secure_cookie
        else {}
    )
    app = FastAPI(title='QueueSense API', version='1.0.0', lifespan=lifespan, **docs)
    app.state.settings = settings
    app.state.public_status_limiter = SlidingWindowLimiter(limit=600, window_seconds=60)
    app.middleware('http')(headers_and_origin)
    register_exception_handlers(app)
    app.include_router(router)
    if settings.choreo:
        app.state.choreo_verifier = ChoreoVerifier(settings.choreo)
        app.include_router(choreo_router)
    return app

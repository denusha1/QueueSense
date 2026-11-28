"""FastAPI entry point used by Uvicorn, the container, and existing callers."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api.choreo import router as choreo_router
from backend.api.errors import register_exception_handlers
from backend.api.middleware import headers_and_origin
from backend.api.router import router
from backend.automation import lifespan as automation_lifespan
from backend.core.choreo import ChoreoVerifier
from backend.core.config import Settings as Settings
from backend.core.logging import configure_application_logging
from backend.core.observability import METRICS_PATH, HttpTelemetry
from backend.core.rate_limit import SlidingWindowLimiter
from backend.core.security import COOKIE as COOKIE
from backend.core.security import HASHER as HASHER
from backend.core.security import digest as digest
from backend.database import connection as connection, pooled_settings
from backend.schemas.auth import WORKSPACES as WORKSPACES
from backend.schemas.auth import Credentials as Credentials


@asynccontextmanager
async def lifespan(app: FastAPI):
    original = app.state.settings
    async with pooled_settings(original) as settings:
        app.state.settings = settings
        try:
            async with automation_lifespan(app):
                yield
        finally:
            app.state.settings = original


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings.from_env()
        configure_application_logging()
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
    if settings.metrics_bearer_token or settings.request_logs_enabled:
        app.state.telemetry = HttpTelemetry(settings)
        if settings.metrics_bearer_token:
            app.add_api_route(
                METRICS_PATH, app.state.telemetry.scrape, methods=['GET'], include_in_schema=False,
            )
    if settings.choreo:
        app.state.choreo_verifier = ChoreoVerifier(settings.choreo)
        app.include_router(choreo_router)
    return app

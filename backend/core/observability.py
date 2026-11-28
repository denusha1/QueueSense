"""Low-cardinality application HTTP telemetry for one FastAPI worker."""

from hmac import compare_digest
import logging
import re

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, ProcessCollector, generate_latest

from backend.api.request_ids import REQUEST_ID_HEADER
from backend.core.config import Settings
from backend.core.logging import log_event

METRICS_PATH = '/internal/metrics'
LOG = logging.getLogger('queuesense.requests')
METHODS = frozenset(('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'))
TRACEPARENT = re.compile(r'00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}')


def trace_id(request: Request, request_id: str) -> str:
    supplied = request.headers.getlist('traceparent')
    match = TRACEPARENT.fullmatch(supplied[0]) if len(supplied) == 1 else None
    if match and int(match[1], 16) and int(match[2], 16):
        return match[1]
    return request_id.replace('-', '')


class HttpTelemetry:
    def __init__(self, settings: Settings):
        self.log_requests = settings.request_logs_enabled
        self.token = settings.metrics_bearer_token
        self.registry = CollectorRegistry()
        ProcessCollector(registry=self.registry)
        self.requests = Counter(
            'queuesense_http_requests', 'Responses started by FastAPI.',
            ['method', 'route', 'status'], registry=self.registry,
        )
        self.duration = Histogram(
            'queuesense_http_request_duration_seconds', 'Time to response headers.',
            ['method', 'route'], registry=self.registry,
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
        )

    def record(self, request: Request, response: Response, seconds: float) -> None:
        if request.scope['path'] == METRICS_PATH:
            return
        method = request.method if request.method in METHODS else 'OTHER'
        route = getattr(request.scope.get('route'), 'path', '<unmatched>')
        status = response.status_code
        if self.token:
            self.requests.labels(method, route, str(status)).inc()
            self.duration.labels(method, route).observe(seconds)
        if self.log_requests:
            request_id = response.headers[REQUEST_ID_HEADER]
            log_event(
                LOG, logging.INFO, 'http_request',
                request_id=request_id, trace_id=trace_id(request, request_id),
                method=method, route=route, status=status, duration_ms=round(seconds * 1000, 2),
            )

    async def scrape(self, request: Request) -> Response:
        authorization = request.headers.getlist('authorization')
        if len(authorization) != 1 or not compare_digest(
            authorization[0].encode(), ('Bearer ' + self.token).encode(),
        ):
            return Response(status_code=401, headers={'WWW-Authenticate': 'Bearer'})
        return Response(generate_latest(self.registry), media_type=CONTENT_TYPE_LATEST)

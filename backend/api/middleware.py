"""Request correlation, common security headers, and origin validation."""

from fastapi import Request

from backend.api.errors import error_response, unexpected_error
from backend.api.request_ids import REQUEST_ID_HEADER, assign_request_id
from backend.core.errors import ServiceError


async def headers_and_origin(request: Request, call_next):
    request_id = assign_request_id(request)
    settings = request.app.state.settings
    origins = request.headers.getlist('origin')
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and (
        len(origins) != 1 or origins[0] not in settings.origins
    ):
        response = error_response(request, 403, 'Request origin is not allowed.')
    else:
        try:
            if request.url.path.startswith(('/patient/', '/self-checkin/')):
                request.app.state.public_status_limiter.check()
            response = await call_next(request)
        except ServiceError as exc:
            response = error_response(
                request, exc.status_code, exc.detail, headers=exc.headers
            )
        except Exception as exc:
            response = unexpected_error(request, exc)

    response.headers[REQUEST_ID_HEADER] = request_id
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    if not response.headers.get('Content-Type', '').startswith('text/html'):
        response.headers['Content-Security-Policy'] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
    if settings.secure_cookie:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response

"""Request correlation, common security headers, and origin validation."""

from fastapi import Request

from backend.api.errors import error_response, unexpected_error
from backend.api.request_ids import REQUEST_ID_HEADER, assign_request_id


async def headers_and_origin(request: Request, call_next):
    request_id = assign_request_id(request)
    settings = request.app.state.settings
    if (
        request.method in ('POST', 'PUT', 'PATCH', 'DELETE')
        and request.headers.get('origin') not in settings.origins
    ):
        response = error_response(request, 403, 'Request origin is not allowed.')
    else:
        try:
            response = await call_next(request)
        except Exception as exc:
            response = unexpected_error(request, exc)

    response.headers[REQUEST_ID_HEADER] = request_id
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    if settings.secure_cookie:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response

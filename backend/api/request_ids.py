"""Request identifiers for correlation across the web proxy and the API."""

import re
from uuid import uuid4

from fastapi import Request

REQUEST_ID_HEADER = 'X-Request-ID'
UUID4 = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'
)


def assign_request_id(request: Request) -> str:
    supplied = request.headers.getlist(REQUEST_ID_HEADER)
    candidate = (
        supplied[0].lower() if len(supplied) == 1 and len(supplied[0]) == 36 else ''
    )
    request_id = candidate if UUID4.fullmatch(candidate) else str(uuid4())
    request.state.request_id = request_id
    return request_id

"""Errors raised by use cases and translated at the HTTP boundary."""

from collections.abc import Mapping


class ServiceError(Exception):
    def __init__(
        self, status_code: int, detail: str, headers: Mapping[str, str] | None = None
    ):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers

"""Shared HTTP error response schemas."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    field: str
    code: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[ValidationIssue] = Field(default_factory=list)


class ApiError(BaseModel):
    success: Literal[False]
    error: ErrorDetail
    request_id: UUID


class LegacyValidationIssue(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class LegacyApiError(ApiError):
    detail: str | list[LegacyValidationIssue]

"""Common versioned OpenAPI response declarations."""

from backend.api.errors import V1_PREFIX, error_models

PREFIX = V1_PREFIX
COMMON_ERRORS = error_models()

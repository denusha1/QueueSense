"""Verify assertions for one approved Choreo proxy and department."""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

import jwt

from backend.core.errors import ServiceError

CONTEXT_CLAIM = 'http://wso2.org/claims/apicontext'
ASSERTION_HEADER = 'X-JWT-Assertion'


@dataclass(frozen=True)
class ChoreoSettings:
    jwks_url: str
    issuer: str
    audience: str
    api_context: str
    department_id: UUID

    @classmethod
    def from_env(cls):
        keys = (
            'CHOREO_JWKS_URL',
            'CHOREO_ASSERTION_ISSUER',
            'CHOREO_ASSERTION_AUDIENCE',
            'CHOREO_ASSERTION_CONTEXT',
            'CHOREO_DEPARTMENT_ID',
        )
        fields = [os.environ.get(key, '').strip() for key in keys]
        if not any(fields):
            return None
        if not all(fields):
            raise RuntimeError('Configure all five CHOREO integration settings')
        url, issuer, audience, context, department = fields
        try:
            parsed = urlsplit(url)
            if (
                parsed.scheme != 'https'
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in (None, 443)
                or parsed.path != '/.wellknown/jwks'
                or any(char.isspace() or char in '\\?#' for char in url)
                or not context.startswith('/')
                or audience == issuer
            ):
                raise ValueError
            department_id = UUID(department)
        except ValueError:
            raise RuntimeError(
                'Invalid Choreo JWKS URL, assertion scope or department ID'
            ) from None
        return cls(url, issuer, audience, context, department_id)


class ChoreoVerifier:
    def __init__(self, settings: ChoreoSettings):
        self.settings = settings
        self.keys = jwt.PyJWKClient(settings.jwks_url, timeout=3, lifespan=300)

    def authorize(self, assertions: list[str]) -> UUID:
        if len(assertions) != 1 or not 0 < len(assertions[0]) <= 8192:
            raise ServiceError(401, 'A valid gateway assertion is required.')
        assertion = assertions[0]
        try:
            header = jwt.get_unverified_header(assertion)
            kid = header.get('kid')
            if (
                header.get('alg') != 'RS256'
                or not isinstance(kid, str)
                or not 0 < len(kid) <= 256
            ):
                raise ValueError
            key = self.keys.get_signing_key(kid)
            claims = jwt.decode(
                assertion,
                key,
                algorithms=['RS256'],
                issuer=self.settings.issuer,
                audience=self.settings.audience,
                options={'require': ['iss', 'aud', 'iat', 'exp', 'jti']},
            )
            issued_at, expires_at = claims['iat'], claims['exp']
            if (
                type(issued_at) is not int
                or type(expires_at) is not int
                or issued_at >= expires_at
            ):
                raise ValueError
        except jwt.PyJWKClientConnectionError:
            raise ServiceError(
                503, 'Gateway signing keys are temporarily unavailable.'
            ) from None
        except (jwt.PyJWTError, ValueError, TypeError, OverflowError):
            raise ServiceError(401, 'A valid gateway assertion is required.') from None
        if claims.get(CONTEXT_CLAIM) != self.settings.api_context:
            raise ServiceError(403, 'This gateway proxy is not authorized.')
        return self.settings.department_id

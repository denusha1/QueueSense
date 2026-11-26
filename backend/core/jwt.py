"""Issue and exclusively validate QueueSense staff access JWTs."""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

import jwt

from backend.core.config import JwtSettings
from backend.core.errors import ServiceError

ALGORITHM = 'HS256'
ACCESS_TYPE = 'at+jwt'
INVALID_TOKEN = 'Your session has ended. Please sign in again.'
REQUIRED_CLAIMS = ['iss', 'aud', 'sub', 'sid', 'jti', 'iat', 'nbf', 'exp', 'token_use']


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID
    expires_at: datetime


def issue_access_token(
    config: JwtSettings,
    user_id: str,
    session_id: UUID,
    session_expires_at: datetime,
) -> tuple[str, datetime]:
    now = int(datetime.now(timezone.utc).timestamp())
    expires = min(now + config.access_seconds, int(session_expires_at.timestamp()))
    if expires <= now:
        raise ServiceError(401, INVALID_TOKEN)
    token = jwt.encode(
        {
            'iss': config.issuer,
            'aud': config.audience,
            'sub': user_id,
            'sid': str(session_id),
            'jti': str(uuid4()),
            'iat': now,
            'nbf': now,
            'exp': expires,
            'token_use': 'access',
        },
        config.signing_key,
        algorithm=ALGORITHM,
        headers={'typ': ACCESS_TYPE},
    )
    return token, datetime.fromtimestamp(expires, timezone.utc)


def verify_access_token(config: JwtSettings, token: str) -> AccessClaims:
    if not token or len(token) > 2048:
        raise ServiceError(401, INVALID_TOKEN)
    try:
        decoded = jwt.decode_complete(
            token,
            config.signing_key,
            algorithms=[ALGORITHM],
            issuer=config.issuer,
            audience=config.audience,
            options={'require': REQUIRED_CLAIMS, 'strict_aud': True},
        )
        claims = decoded['payload']
        if (
            decoded['header'] != {'alg': ALGORITHM, 'typ': ACCESS_TYPE}
            or claims['token_use'] != 'access'
        ):
            raise ValueError
        if any(type(claims[name]) is not int for name in ('iat', 'nbf', 'exp')):
            raise ValueError
        if (
            claims['nbf'] != claims['iat']
            or not 0 < claims['exp'] - claims['iat'] <= config.access_seconds
        ):
            raise ValueError
        user_id, session_id, token_id = (
            UUID(claims[name]) for name in ('sub', 'sid', 'jti')
        )
        if (str(user_id), str(session_id), str(token_id)) != (
            claims['sub'],
            claims['sid'],
            claims['jti'],
        ):
            raise ValueError
        return AccessClaims(
            user_id, session_id, datetime.fromtimestamp(claims['exp'], timezone.utc)
        )
    except (jwt.PyJWTError, ValueError, TypeError, OverflowError, AttributeError):
        raise ServiceError(401, INVALID_TOKEN) from None

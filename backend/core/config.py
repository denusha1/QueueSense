"""Configuration shared by HTTP handlers, workers, and provider adapters."""

import base64
import binascii
import os
import re
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

CLINIC_TIMEZONE = ZoneInfo('Asia/Colombo')
DEFAULT_ORIGINS = 'http://127.0.0.1:3001,http://localhost:3001'


@dataclass(frozen=True)
class JwtSettings:
    signing_key: bytes = field(repr=False)
    issuer: str
    audience: str
    access_seconds: int = 600
    refresh_seconds: int = 28_800

    @classmethod
    def from_env(cls, *, required: bool) -> 'JwtSettings | None':
        encoded = os.environ.get('JWT_SIGNING_SECRET', '')
        if not encoded:
            if required:
                raise RuntimeError('JWT_SIGNING_SECRET is required in production')
            return None
        try:
            if not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}', encoded):
                raise ValueError
            signing_key = base64.b64decode(
                encoded + '=' * (-len(encoded) % 4),
                altchars=b'-_',
                validate=True,
            )
        except (ValueError, binascii.Error):
            raise RuntimeError(
                'JWT_SIGNING_SECRET must encode at least 32 random bytes as URL-safe Base64'
            ) from None
        if len(signing_key) < 32:
            raise RuntimeError(
                'JWT_SIGNING_SECRET must encode at least 32 random bytes as URL-safe Base64'
            )
        issuer = os.environ.get('JWT_ISSUER', 'queuesense-staff').strip()
        audience = os.environ.get('JWT_AUDIENCE', 'queuesense-private-api').strip()
        if (
            not 0 < len(issuer) <= 200
            or not 0 < len(audience) <= 200
            or any(ord(char) < 32 for char in issuer + audience)
        ):
            raise RuntimeError(
                'JWT_ISSUER and JWT_AUDIENCE must be nonempty identifiers'
            )
        access = positive_setting('JWT_ACCESS_TTL_SECONDS', 600, 900, minimum=60)
        refresh = positive_setting(
            'JWT_REFRESH_TTL_SECONDS', 28_800, 86_400, minimum=300
        )
        if refresh <= access:
            raise RuntimeError(
                'JWT_REFRESH_TTL_SECONDS must exceed JWT_ACCESS_TTL_SECONDS'
            )
        return cls(signing_key, issuer, audience, access, refresh)


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    origins: tuple[str, ...]
    secure_cookie: bool = False
    demo_enabled: bool = False
    session_seconds: int = 8 * 60 * 60
    automation_enabled: bool = True
    db_connect_timeout_seconds: int = 5
    db_statement_timeout_ms: int = 20_000
    db_lock_timeout_ms: int = 5_000
    jwt: JwtSettings | None = None

    @classmethod
    def from_env(cls) -> 'Settings':
        url = os.environ.get('DATABASE_URL', '')
        if not url:
            raise RuntimeError('DATABASE_URL is required')
        production = is_production()
        origins = tuple(
            value.strip().rstrip('/')
            for value in os.environ.get('FRONTEND_ORIGINS', DEFAULT_ORIGINS).split(',')
            if value.strip()
        )
        demo = os.environ.get('ENABLE_DEMO_LOGIN') == 'true'
        if production and (
            demo or any(not origin.startswith('https://') for origin in origins)
        ):
            raise RuntimeError(
                'Production requires HTTPS origins and disabled demo login'
            )
        if not origins:
            raise RuntimeError('At least one frontend origin is required')
        return cls(
            url,
            origins,
            production,
            demo,
            automation_enabled=os.environ.get('ENABLE_AUTOMATION', 'true') == 'true',
            db_connect_timeout_seconds=positive_setting(
                'DB_CONNECT_TIMEOUT_SECONDS', 5, 60, minimum=2
            ),
            db_statement_timeout_ms=positive_setting(
                'DB_STATEMENT_TIMEOUT_MS', 20_000, 600_000
            ),
            db_lock_timeout_ms=positive_setting('DB_LOCK_TIMEOUT_MS', 5_000, 600_000),
            jwt=JwtSettings.from_env(required=production),
        )


def positive_setting(name: str, default: int, maximum: int, *, minimum: int = 1) -> int:
    message = f'{name} must be an integer from {minimum} to {maximum}'
    try:
        value = int(os.environ.get(name, default))
    except ValueError:
        raise RuntimeError(message) from None
    if not minimum <= value <= maximum:
        raise RuntimeError(message)
    return value


def is_production() -> bool:
    return os.environ.get('APP_ENV') == 'production'


def account_encryption_key() -> str | None:
    return os.environ.get('ACCOUNT_ENCRYPTION_KEY')


@dataclass(frozen=True, repr=False)
class DeliverySettings:
    smtp_host: str
    smtp_port: str
    smtp_ssl: bool
    smtp_from: str
    smtp_user: str
    smtp_password: str
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from: str
    vapid_public_key: str
    vapid_private_key: str
    vapid_subject: str
    push_allowed_hosts: frozenset[str]

    @classmethod
    def from_env(cls) -> 'DeliverySettings':
        env = os.environ
        return cls(
            smtp_host=env.get('SMTP_HOST', ''),
            smtp_port=env.get('SMTP_PORT', '587'),
            smtp_ssl=env.get('SMTP_SSL') == 'true',
            smtp_from=env.get('SMTP_FROM', ''),
            smtp_user=env.get('SMTP_USER', ''),
            smtp_password=env.get('SMTP_PASSWORD', ''),
            twilio_account_sid=env.get('TWILIO_ACCOUNT_SID', ''),
            twilio_auth_token=env.get('TWILIO_AUTH_TOKEN', ''),
            twilio_from=env.get('TWILIO_FROM', ''),
            vapid_public_key=env.get('VAPID_PUBLIC_KEY', ''),
            vapid_private_key=env.get('VAPID_PRIVATE_KEY', ''),
            vapid_subject=env.get('VAPID_SUBJECT', ''),
            push_allowed_hosts=frozenset(env.get('PUSH_ALLOWED_HOSTS', '').split(',')),
        )

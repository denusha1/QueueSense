"""Credential primitives and shared staff authorization rules."""

import hashlib
import re
import secrets
from typing import Literal

from argon2 import PasswordHasher

from backend.core.errors import ServiceError

Role = Literal['reception', 'doctor', 'manager', 'admin']
COOKIE = 'queuesense_session'
REFRESH_COOKIE = 'queuesense_refresh'
HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))
OPS = ('admin', 'reception', 'doctor')
MANAGERS = ('admin', 'manager')


PRIVATE_KEY_PATTERN = r'^[A-Za-z0-9_-]{30,80}$'


def valid_private_key(key: str) -> bool:
    return re.fullmatch(PRIVATE_KEY_PATTERN, key) is not None


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def require(user, roles):
    if user['role'] not in roles:
        raise ServiceError(
            403, 'Your account does not have permission for this action.'
        )

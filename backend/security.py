"""Encrypted application secrets and replay-resistant RFC 6238 codes."""

import base64
import hashlib
import hmac
import os
import struct
import time
from pathlib import Path

from cryptography.fernet import Fernet

from backend.core.config import account_encryption_key, is_production
from backend.core.errors import ServiceError


def cipher():
    key = account_encryption_key()
    if not key:
        if is_production():
            raise ServiceError(503, 'Account encryption is not configured.')
        path = Path(__file__).resolve().parents[1] / '.local/account-key'
        path.parent.mkdir(exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(Fernet.generate_key())
        except FileExistsError:
            pass
        key = path.read_bytes()
    return Fernet(key)


def encrypt(value):
    return cipher().encrypt(value.encode()).decode()


def decrypt(value):
    return cipher().decrypt(value.encode()).decode()


def code_hash(value):
    return hmac.new(cipher()._signing_key, value.encode(), hashlib.sha256).hexdigest()


def totp(secret, step=None):
    step = int(time.time() / 30) if step is None else step
    raw = hmac.new(
        base64.b32decode(secret), struct.pack('>Q', step), hashlib.sha1
    ).digest()
    offset = raw[-1] & 15
    return str(
        (struct.unpack('>I', raw[offset : offset + 4])[0] & 0x7FFFFFFF) % 1000000
    ).zfill(6)


def verify_totp(secret, code, last_step=-1):
    if not code or len(code) != 6 or not code.isdigit():
        return None
    now = int(time.time() / 30)
    for step in (now, now - 1, now + 1):
        if step > last_step and hmac.compare_digest(totp(secret, step), code):
            return step
    return None


def throttle(conn, bucket, maximum=5):
    # Serialise the count with caller transactions and retain denied attempts.
    conn.execute('SELECT pg_advisory_xact_lock(72419028)')
    conn.execute(
        "DELETE FROM security_attempts WHERE created_at<now()-interval '1 day'"
    )
    count = conn.execute(
        "SELECT count(*) AS n FROM security_attempts WHERE bucket=%s AND created_at>now()-interval '15 minutes'",
        (bucket,),
    ).fetchone()['n']
    conn.execute('INSERT INTO security_attempts(bucket) VALUES(%s)', (bucket,))
    return count < maximum

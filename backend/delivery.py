"""Opt-in verified destinations, durable retries and generic external messages."""

import json
import re
import secrets
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from backend.core.config import DeliverySettings
from backend.core.errors import ServiceError
from backend.core.security import valid_private_key
from backend.database import connection
from backend.schemas.text import SingleLine
from backend.security import code_hash, decrypt, encrypt, throttle

GENERIC = 'QueueSense: You have an update from your clinic. Open your queue tracking page or staff workspace to view it.'


def capabilities(config: DeliverySettings | None = None):
    config = config or DeliverySettings.from_env()
    return {
        'email': bool(config.smtp_host and config.smtp_from),
        'sms': bool(
            config.twilio_account_sid
            and config.twilio_auth_token
            and config.twilio_from
        ),
        'push': bool(
            config.vapid_private_key
            and config.vapid_public_key
            and config.vapid_subject
        ),
        'vapid_public_key': config.vapid_public_key,
    }


def mail(address, text):
    config = DeliverySettings.from_env()
    msg = EmailMessage()
    msg['From'] = config.smtp_from
    msg['To'] = address
    msg['Subject'] = 'QueueSense account or clinic update'
    msg.set_content(text)
    transport = smtplib.SMTP_SSL if config.smtp_ssl else smtplib.SMTP
    with transport(config.smtp_host, int(config.smtp_port), timeout=8) as smtp:
        if not config.smtp_ssl:
            smtp.starttls()
        if config.smtp_user:
            smtp.login(config.smtp_user, config.smtp_password)
        smtp.send_message(msg)


def send(channel, destination, text=GENERIC, url='/patient'):
    config = DeliverySettings.from_env()
    if not capabilities(config).get(channel):
        raise RuntimeError('provider_unconfigured')
    if channel == 'email':
        mail(destination, text)
    elif channel == 'sms':
        sid = config.twilio_account_sid
        if not re.fullmatch(r'AC[a-fA-F0-9]{32}', sid):
            raise RuntimeError('invalid_provider_configuration')
        with httpx.Client(timeout=8, follow_redirects=False) as client:
            response = client.post(
                'https://api.twilio.com/2010-04-01/Accounts/' + sid + '/Messages.json',
                auth=(sid, config.twilio_auth_token),
                data={'From': config.twilio_from, 'To': destination, 'Body': text},
            )
            response.raise_for_status()
    else:
        from pywebpush import webpush

        webpush(
            json.loads(destination),
            data=json.dumps(
                {'title': 'QueueSense update', 'body': GENERIC, 'url': url}
            ),
            vapid_private_key=config.vapid_private_key,
            vapid_claims={'sub': config.vapid_subject},
            timeout=8,
        )


def run_delivery(settings):
    with connection(settings) as conn:
        # Only notifications after verified opt-in are eligible. No old-message replay.
        conn.execute("""INSERT INTO notification_deliveries(notification_id,target_id)
        SELECT n.id,t.id FROM notifications n JOIN notification_targets t ON t.enabled AND t.verified_at IS NOT NULL AND n.created_at>=t.verified_at
        AND ((t.owner_type='patient' AND n.token_id=t.owner_id) OR (t.owner_type='appointment' AND n.appointment_id=t.owner_id) OR (t.owner_type='staff' AND n.audience='staff'))
        LEFT JOIN users u ON t.owner_type='staff' AND u.id=t.owner_id
        WHERE t.owner_type!='staff' OR u.is_active ON CONFLICT DO NOTHING""")
    with connection(settings) as conn:
        if not conn.execute(
            'SELECT pg_try_advisory_xact_lock(72419029) AS acquired'
        ).fetchone()['acquired']:
            return
        rows = conn.execute(
            "SELECT j.*,t.channel,t.destination_encrypted,t.enabled,t.verified_at,t.owner_type,n.created_at AS notification_created_at FROM notification_deliveries j JOIN notification_targets t ON t.id=j.target_id JOIN notifications n ON n.id=j.notification_id WHERE j.state='pending' AND j.next_attempt<=now() ORDER BY j.next_attempt LIMIT 20 FOR UPDATE OF j SKIP LOCKED"
        ).fetchall()
        for row in rows:
            if (
                not row['enabled']
                or not row['verified_at']
                or row['notification_created_at'] < row['verified_at']
            ):
                conn.execute(
                    "UPDATE notification_deliveries SET state='cancelled' WHERE id=%s",
                    (row['id'],),
                )
                continue
            try:
                send(
                    row['channel'],
                    decrypt(row['destination_encrypted']),
                    url='/' if row['owner_type'] == 'staff' else '/patient',
                )
            except Exception as exc:
                # Never persist provider response bodies, destination data or credentials.
                attempts = row['attempts'] + 1
                conn.execute(
                    "UPDATE notification_deliveries SET attempts=%s,state=%s,next_attempt=now()+%s*interval '1 second',last_error=%s WHERE id=%s",
                    (
                        attempts,
                        'failed' if attempts >= 5 else 'pending',
                        min(3600, 30 * 2**attempts),
                        type(exc).__name__,
                        row['id'],
                    ),
                )
            else:
                conn.execute(
                    "UPDATE notification_deliveries SET state='sent',attempts=attempts+1,sent_at=now(),last_error=NULL WHERE id=%s",
                    (row['id'],),
                )


class Target(BaseModel):
    model_config = ConfigDict(extra='forbid')
    channel: str
    destination: SingleLine = Field(max_length=254)
    consent: bool


class Verify(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str = Field(min_length=6, max_length=6)


class Subscription(BaseModel):
    model_config = ConfigDict(extra='forbid')
    endpoint: SingleLine = Field(max_length=2048)
    keys: dict[str, str]
    consent: bool


def owner(settings, scope, key, user):
    if scope == 'staff':
        return user['id']
    if not valid_private_key(key):
        raise ServiceError(404, 'Private link not found.')
    table = 'queue_tokens' if scope == 'patient' else 'appointments'
    with connection(settings) as conn:
        row = conn.execute(
            'SELECT id FROM ' + table + ' WHERE public_key=%s', (key,)
        ).fetchone()
    if not row:
        raise ServiceError(404, 'Private link not found.')
    return row['id']


def list_targets(settings, scope, key, user):
    oid = owner(settings, scope, key, user)
    with connection(settings) as conn:
        rows = conn.execute(
            'SELECT id,channel,masked,enabled,verified_at FROM notification_targets WHERE owner_type=%s AND owner_id=%s ORDER BY channel',
            (scope, oid),
        ).fetchall()
    for row in rows:
        row['verified'] = row['verified_at'] is not None
    return {'capabilities': capabilities(), 'targets': rows}


def register(settings, scope, key, user, body):
    oid = owner(settings, scope, key, user)
    if not body.consent or body.channel not in ('email', 'sms'):
        raise ServiceError(
            422, 'Explicit consent and a supported channel are required.'
        )
    if not capabilities().get(body.channel):
        raise ServiceError(503, 'This notification provider is not configured.')
    destination = (
        body.destination.strip().lower()
        if body.channel == 'email'
        else body.destination.strip()
    )
    if body.channel == 'email' and not re.fullmatch(
        r'[^\s@]+@[^\s@]+\.[^\s@]+', destination
    ):
        raise ServiceError(422, 'Enter a valid email address.')
    if body.channel == 'sms' and not re.fullmatch(r'\+[1-9][0-9]{7,14}', destination):
        raise ServiceError(422, 'Enter a phone number in international format.')
    with connection(settings) as conn:
        allowed = throttle(conn, 'contact:' + scope + ':' + str(oid), 3)
    if not allowed:
        raise ServiceError(429, 'Try again in 15 minutes.')
    encrypted = encrypt(destination)
    code = str(secrets.randbelow(1000000)).zfill(6)
    try:
        send(
            body.channel,
            destination,
            'QueueSense verification code: '
            + code
            + '. Expires in 10 minutes. Do not share it.',
        )
    except Exception:
        raise ServiceError(503, 'Verification delivery failed. Try again later.')
    masked = (
        destination[:1] + '***@' + destination.split('@')[1]
        if body.channel == 'email'
        else '***' + destination[-4:]
    )
    with connection(settings) as conn:
        conn.execute(
            "INSERT INTO notification_targets(owner_type,owner_id,channel,destination_encrypted,masked,verification_hash,verification_expires) VALUES(%s,%s,%s,%s,%s,%s,now()+interval '10 minutes') ON CONFLICT(owner_type,owner_id,channel) DO UPDATE SET destination_encrypted=excluded.destination_encrypted,masked=excluded.masked,verification_hash=excluded.verification_hash,verification_expires=excluded.verification_expires,verification_attempts=0,verified_at=NULL,enabled=false",
            (
                scope,
                oid,
                body.channel,
                encrypted,
                masked,
                code_hash(str(oid) + ':' + code),
            ),
        )
    return {'ok': True, 'message': 'Verification code sent.'}


def verify(settings, scope, key, user, channel, body):
    oid = owner(settings, scope, key, user)
    valid = False
    with connection(settings) as conn:
        row = conn.execute(
            'SELECT * FROM notification_targets WHERE owner_type=%s AND owner_id=%s AND channel=%s FOR UPDATE',
            (scope, oid, channel),
        ).fetchone()
        if (
            row
            and row['verification_hash']
            and row['verification_attempts'] < 5
            and row['verification_expires'] > datetime.now(timezone.utc)
        ):
            import hmac

            valid = hmac.compare_digest(
                row['verification_hash'], code_hash(str(oid) + ':' + body.code)
            )
            conn.execute(
                'UPDATE notification_targets SET verification_attempts=verification_attempts+1 WHERE id=%s',
                (row['id'],),
            )
            if valid:
                conn.execute(
                    'UPDATE notification_targets SET enabled=true,verified_at=now(),verification_hash=NULL WHERE id=%s',
                    (row['id'],),
                )
    if not valid:
        raise ServiceError(400, 'Verification code is invalid or expired.')
    return {'ok': True}


def disable(settings, scope, key, user, channel):
    oid = owner(settings, scope, key, user)
    with connection(settings) as conn:
        conn.execute(
            'DELETE FROM notification_targets WHERE owner_type=%s AND owner_id=%s AND channel=%s',
            (scope, oid, channel),
        )
    return {'ok': True}


def push(settings, scope, key, user, body):
    oid = owner(settings, scope, key, user)
    if not body.consent or not capabilities()['push']:
        raise ServiceError(
            503, 'Background push is not configured or consent was not supplied.'
        )
    try:
        url = urlparse(body.endpoint)
        port = url.port
    except ValueError:
        raise ServiceError(422, 'Unsupported push endpoint.')
    allowed = {
        'fcm.googleapis.com',
        'updates.push.services.mozilla.com',
        'web.push.apple.com',
    } | DeliverySettings.from_env().push_allowed_hosts
    if (
        url.scheme != 'https'
        or url.hostname not in allowed
        or url.username
        or url.password
        or port not in (None, 443)
        or set(body.keys) != {'auth', 'p256dh'}
    ):
        raise ServiceError(422, 'Unsupported push endpoint.')
    import base64

    try:
        if (
            len(base64.urlsafe_b64decode(body.keys['p256dh'] + '===')) != 65
            or len(base64.urlsafe_b64decode(body.keys['auth'] + '===')) != 16
        ):
            raise ValueError()
    except Exception:
        raise ServiceError(422, 'Invalid push subscription keys.')
    with connection(settings) as conn:
        conn.execute(
            "INSERT INTO notification_targets(owner_type,owner_id,channel,destination_encrypted,masked,enabled,verified_at) VALUES(%s,%s,'push',%s,'This browser',true,now()) ON CONFLICT(owner_type,owner_id,channel) DO UPDATE SET destination_encrypted=excluded.destination_encrypted,enabled=true,verified_at=now()",
            (
                scope,
                oid,
                encrypt(json.dumps({'endpoint': body.endpoint, 'keys': body.keys})),
            ),
        )
    return {'ok': True}

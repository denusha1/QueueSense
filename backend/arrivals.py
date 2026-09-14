"""Capacity-limited appointments, idempotent QR arrivals and committed queue events."""
import secrets
import time
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg
from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from psycopg import sql
from pydantic import Field
from reportlab.graphics import renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing

from backend.app import connection, COOKIE, digest
from backend.product import Input, require, audit

TZ = ZoneInfo('Asia/Colombo')
ROLES = ('admin', 'reception')


class SlotInput(Input):
    department_id: uuid.UUID
    starts_at: datetime
    capacity: int = Field(default=1, ge=1, le=20)


class BookingInput(Input):
    slot_id: uuid.UUID


class SelfInput(Input):
    request_id: uuid.UUID


class KioskInput(Input):
    department_id: uuid.UUID


def attach_arrivals(app, settings, current_user, issue_token):
    @app.get('/appointments/slots')
    def slots(day: date, department: uuid.UUID | None = None, user=Depends(current_user)):
        require(user, ROLES)
        with connection(settings) as conn:
            return conn.execute("""SELECT s.*,d.name AS department,count(a.id) FILTER (WHERE a.status!='cancelled') AS booked
            FROM appointment_slots s JOIN departments d ON d.id=s.department_id LEFT JOIN appointments a ON a.slot_id=s.id
            WHERE (s.starts_at AT TIME ZONE 'Asia/Colombo')::date=%s AND (%s::uuid IS NULL OR s.department_id=%s)
            GROUP BY s.id,d.name ORDER BY s.starts_at,d.name""", (day,department,department)).fetchall()

    @app.post('/appointments/slots', status_code=201)
    def create_slot(body: SlotInput, user=Depends(current_user)):
        require(user, ROLES)
        now=datetime.now(TZ)
        if body.starts_at.tzinfo is None or not now < body.starts_at <= now+timedelta(days=90):
            raise HTTPException(422,'Choose a future slot within 90 days, with a timezone.')
        local=body.starts_at.astimezone(TZ)
        if local.minute not in (0,30) or local.second or local.microsecond:
            raise HTTPException(422,'Slots start on the hour or half hour in Asia/Colombo.')
        with connection(settings) as conn:
            if not conn.execute('SELECT 1 FROM departments WHERE id=%s AND is_active',(body.department_id,)).fetchone():
                raise HTTPException(404,'Department unavailable.')
            row=conn.execute('INSERT INTO appointment_slots(department_id,starts_at,capacity,created_by) VALUES(%s,%s,%s,%s) ON CONFLICT(department_id,starts_at) DO NOTHING RETURNING *',(body.department_id,body.starts_at,body.capacity,user['id'])).fetchone()
            if not row: raise HTTPException(409,'A slot already exists at that time.')
            audit(conn,user,'create_appointment_slot','appointment_slot',row['id'])
            return row

    @app.get('/appointments')
    def appointments(day: date, user=Depends(current_user)):
        require(user, ROLES)
        with connection(settings) as conn:
            return conn.execute("""SELECT a.*,s.starts_at,d.name AS department FROM appointments a
            JOIN appointment_slots s ON s.id=a.slot_id JOIN departments d ON d.id=s.department_id
            WHERE (s.starts_at AT TIME ZONE 'Asia/Colombo')::date=%s ORDER BY s.starts_at,a.created_at""",(day,)).fetchall()

    @app.post('/appointments', status_code=201)
    def book(body: BookingInput, user=Depends(current_user)):
        require(user, ROLES)
        with connection(settings) as conn:
            slot=conn.execute('SELECT s.*,d.is_active FROM appointment_slots s JOIN departments d ON d.id=s.department_id WHERE s.id=%s FOR UPDATE OF s',(body.slot_id,)).fetchone()
            if not slot or not slot['is_active']: raise HTTPException(404,'Slot unavailable.')
            if slot['starts_at']<=datetime.now(TZ): raise HTTPException(409,'This slot has already started.')
            count=conn.execute("SELECT count(*) AS n FROM appointments WHERE slot_id=%s AND status!='cancelled'",(body.slot_id,)).fetchone()['n']
            if count>=slot['capacity']: raise HTTPException(409,'This slot is full. Choose another time.')
            row=conn.execute('INSERT INTO appointments(slot_id,reference,public_key,created_by) VALUES(%s,%s,%s,%s) RETURNING *',(body.slot_id,'APT-'+secrets.token_hex(5).upper(),secrets.token_urlsafe(32),user['id'])).fetchone()
            audit(conn,user,'book_appointment','appointment',row['id'])
            return row

    @app.post('/appointments/{appointment_id}/cancel')
    def cancel(appointment_id: uuid.UUID, user=Depends(current_user)):
        require(user, ROLES)
        with connection(settings) as conn:
            row=conn.execute("UPDATE appointments SET status='cancelled' WHERE id=%s AND status='booked' RETURNING *",(appointment_id,)).fetchone()
            if not row: raise HTTPException(409,'Only booked appointments can be cancelled.')
            audit(conn,user,'cancel_appointment','appointment',row['id'])
            return row

    @app.get('/checkin/kiosks')
    def kiosks(user=Depends(current_user)):
        require(user, ROLES)
        with connection(settings) as conn:
            return conn.execute('SELECT k.*,d.name AS department FROM checkin_kiosks k JOIN departments d ON d.id=k.department_id WHERE expires_at>now() AND revoked_at IS NULL ORDER BY d.name').fetchall()

    @app.post('/checkin/kiosks', status_code=201)
    def create_kiosk(body: KioskInput, user=Depends(current_user)):
        require(user, ROLES)
        with connection(settings) as conn:
            conn.execute('SELECT pg_advisory_xact_lock(72419023)')
            if not conn.execute('SELECT 1 FROM departments WHERE id=%s AND is_active',(body.department_id,)).fetchone(): raise HTTPException(404,'Department unavailable.')
            existing=conn.execute('SELECT * FROM checkin_kiosks WHERE department_id=%s AND expires_at>now() AND revoked_at IS NULL',(body.department_id,)).fetchone()
            if existing: return existing
            expires=(datetime.now(TZ)+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
            row=conn.execute('INSERT INTO checkin_kiosks(department_id,public_key,expires_at,created_by) VALUES(%s,%s,%s,%s) RETURNING *',(body.department_id,secrets.token_urlsafe(32),expires,user['id'])).fetchone()
            audit(conn,user,'create_checkin_qr','checkin_kiosk',row['id'])
            return row

    @app.post('/checkin/kiosks/{kiosk_id}/revoke')
    def revoke(kiosk_id: uuid.UUID, user=Depends(current_user)):
        require(user, ROLES)
        with connection(settings) as conn:
            row=conn.execute('UPDATE checkin_kiosks SET revoked_at=now() WHERE id=%s RETURNING id',(kiosk_id,)).fetchone()
            if not row: raise HTTPException(404,'QR code not found.')
            audit(conn,user,'revoke_checkin_qr','checkin_kiosk',row['id'])
            return {'ok':True}

    def resolve(conn, key, lock=False):
        if not 30<=len(key)<=80: raise HTTPException(404,'Check-in link not found.')
        row=conn.execute("""SELECT a.id,a.reference,a.status,a.token_id,s.starts_at,s.department_id,d.name AS department,d.is_active
        FROM appointments a JOIN appointment_slots s ON s.id=a.slot_id JOIN departments d ON d.id=s.department_id
        WHERE a.public_key=%s"""+(' FOR UPDATE OF a' if lock else ''),(key,)).fetchone()
        if row: return 'appointment',row
        row=conn.execute('SELECT k.*,d.name AS department,d.is_active FROM checkin_kiosks k JOIN departments d ON d.id=k.department_id WHERE k.public_key=%s'+(' FOR UPDATE OF k' if lock else ''),(key,)).fetchone()
        if not row: raise HTTPException(404,'Check-in link not found.')
        if row['revoked_at'] or row['expires_at']<=datetime.now(TZ): raise HTTPException(410,'This QR code has expired. Ask reception for today’s code.')
        return 'walkin',row

    @app.get('/self-checkin/{key}')
    def info(key: str):
        with connection(settings) as conn:
            kind,row=resolve(conn,key)
            return dict(kind=kind,department=row['department'],reference=row.get('reference'),starts_at=row.get('starts_at'),status=row.get('status','open'),active=row['is_active'])

    @app.get('/self-checkin/{key}/qr')
    def qr(key: str, origin: str):
        if origin not in settings.origins: raise HTTPException(422,'Use a configured clinic URL.')
        with connection(settings) as conn: resolve(conn,key)
        widget=QrCodeWidget(origin+'/self-checkin/'+key,barLevel='M')
        x0,y0,x1,y1=widget.getBounds()
        drawing=Drawing(256,256,transform=[256/(x1-x0),0,0,256/(y1-y0),0,0]);drawing.add(widget)
        return Response(renderSVG.drawToString(drawing),media_type='image/svg+xml')

    @app.post('/self-checkin/{key}')
    def self_checkin(key: str, body: SelfInput):
        with connection(settings) as conn:
            # Same lock order as normal check-in; one transaction issues and links the token.
            conn.execute('SELECT pg_advisory_xact_lock(72419023)')
            kind,row=resolve(conn,key,lock=True)
            if not row['is_active']: raise HTTPException(409,'Department unavailable. Contact reception.')
            token_id=row.get('token_id')
            if kind=='appointment':
                if row['status']=='cancelled': raise HTTPException(409,'This appointment was cancelled.')
                if not token_id and not row['starts_at']-timedelta(minutes=30)<=datetime.now(TZ)<row['starts_at']+timedelta(minutes=30):
                    raise HTTPException(409,'Check-in opens 30 minutes before your slot and closes 30 minutes after it starts.')
            else:
                prior=conn.execute('SELECT token_id FROM self_checkins WHERE kiosk_id=%s AND request_id=%s',(row['id'],body.request_id)).fetchone()
                token_id=prior['token_id'] if prior else None
                count=conn.execute("SELECT count(*) AS n FROM self_checkins c JOIN queue_tokens t ON t.id=c.token_id WHERE c.kiosk_id=%s AND t.check_in_at>now()-interval '1 minute'",(row['id'],)).fetchone()['n']
                if not token_id and count>=20: raise HTTPException(429,'Many arrivals just checked in. Please try again in a minute.')
            if token_id:
                token=conn.execute('SELECT public_key FROM queue_tokens WHERE id=%s',(token_id,)).fetchone()
            else:
                token=issue_token(conn,row['department_id'])
                if kind=='appointment': conn.execute("UPDATE appointments SET status='checked_in',token_id=%s WHERE id=%s",(token['id'],row['id']))
                else: conn.execute('INSERT INTO self_checkins(kiosk_id,request_id,token_id) VALUES(%s,%s,%s)',(row['id'],body.request_id,token['id']))
            return {'patient_key':token['public_key']}

    async def events(channel, request, session_hash=None):
        async with await psycopg.AsyncConnection.connect(settings.database_url,autocommit=True) as conn:
            await conn.execute(sql.SQL('LISTEN {}').format(sql.Identifier(channel)))
            yield 'retry: 2000\nevent: ready\ndata: {}\n\n'
            started=time.monotonic()
            while time.monotonic()-started<50:
                if await request.is_disconnected(): break
                if session_hash:
                    cursor=await conn.execute('SELECT 1 FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=%s AND s.expires_at>now() AND u.is_active',(session_hash,))
                    if not await cursor.fetchone(): break
                async for notification in conn.notifies(timeout=8,stop_after=1):
                    yield 'event: change\ndata: {}\n\n'
                yield ': heartbeat\n\n'

    @app.get('/queue/events')
    async def queue_events(request: Request, user=Depends(current_user)):
        return StreamingResponse(events('queuesense_queue',request,digest(request.cookies[COOKIE])),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})

    @app.get('/patient/{key}/events')
    def patient_events(key: str, request: Request):
        if not 30<=len(key)<=80: raise HTTPException(404,'Token not found.')
        with connection(settings) as conn:
            row=conn.execute('SELECT department_id FROM queue_tokens WHERE public_key=%s',(key,)).fetchone()
            if not row: raise HTTPException(404,'Token not found.')
        return StreamingResponse(events('queuesense_'+row['department_id'].hex,request),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg
from fastapi.testclient import TestClient
from backend.app import Settings, create_app
from backend.tests.test_auth import client, test_url, login, ORIGIN
from backend.tests.test_product import clinic, post

TZ=ZoneInfo('Asia/Colombo')


def next_slot():
    now=datetime.now(TZ)
    return now.replace(minute=0,second=0,microsecond=0)+timedelta(minutes=30 if now.minute<30 else 60)


def publish(client,dep,when=None,capacity=1):
    response=post(client,'/appointments/slots',dict(department_id=dep['id'],starts_at=(when or next_slot()).isoformat(),capacity=capacity))
    assert response.status_code==201,response.text
    return response.json()


def test_booking_capacity_cancel_and_role_boundaries(client,clinic):
    dep,_=clinic
    slot=publish(client,dep)
    booking=post(client,'/appointments',{'slot_id':slot['id']});assert booking.status_code==201,booking.text
    assert post(client,'/appointments',{'slot_id':slot['id']}).status_code==409
    assert post(client,'/appointments/'+booking.json()['id']+'/cancel').status_code==200
    assert post(client,'/appointments',{'slot_id':slot['id']}).status_code==201
    assert client.get('/appointments?day='+next_slot().date().isoformat()).status_code==200
    assert login(client,'manager').status_code==200
    assert post(client,'/appointments',{'slot_id':slot['id']}).status_code==403
    assert client.get('/appointments/slots?day='+next_slot().date().isoformat()).status_code==403
    assert post(client,'/checkin/kiosks',{'department_id':dep['id']}).status_code==403
    client.cookies.clear()
    assert client.get('/queue/events').status_code==401
    assert client.get('/patient/'+'x'*43+'/events').status_code==404


def test_appointment_self_arrival_is_idempotent_and_private(client,clinic):
    dep,_=clinic
    slot=publish(client,dep)
    booking=post(client,'/appointments',{'slot_id':slot['id']}).json()
    client.cookies.clear()
    path='/self-checkin/'+booking['public_key']
    info=client.get(path);assert info.status_code==200
    assert 'public_key' not in info.json() and 'department_id' not in info.json()
    qr=client.get(path+'/qr',params={'origin':ORIGIN});assert qr.status_code==200 and '<svg' in qr.text
    assert client.get(path+'/qr',params={'origin':'https://malicious.test'}).status_code==422
    first=post(client,path,{'request_id':str(uuid.uuid4())});assert first.status_code==200,first.text
    second=post(client,path,{'request_id':str(uuid.uuid4())});assert second.json()==first.json()
    assert client.get('/patient/'+first.json()['patient_key']).json()['status']=='waiting'
    assert login(client,'admin').status_code==200
    assert post(client,'/appointments/'+booking['id']+'/cancel').status_code==409
    assert len(client.get('/queue/live?department='+dep['id']).json()['tokens'])==1


def test_early_cancelled_closed_and_expired_checkins(client,clinic,test_url):
    dep,_=clinic
    slot=publish(client,dep,next_slot()+timedelta(days=1))
    booking=post(client,'/appointments',{'slot_id':slot['id']}).json()
    path='/self-checkin/'+booking['public_key']
    assert post(client,path,{'request_id':str(uuid.uuid4())}).status_code==409
    assert post(client,'/appointments/'+booking['id']+'/cancel').status_code==200
    assert post(client,path,{'request_id':str(uuid.uuid4())}).status_code==409
    kiosk=post(client,'/checkin/kiosks',{'department_id':dep['id']}).json()
    assert post(client,'/checkin/kiosks',{'department_id':dep['id']}).json()['id']==kiosk['id']
    with psycopg.connect(test_url) as conn:
        conn.execute("UPDATE checkin_kiosks SET expires_at=now()-interval '1 second' WHERE id=%s",(kiosk['id'],))
    assert client.get('/self-checkin/'+kiosk['public_key']).status_code==410
    kiosk=post(client,'/checkin/kiosks',{'department_id':dep['id']}).json()
    assert post(client,'/checkin/kiosks/'+kiosk['id']+'/revoke').status_code==200
    assert post(client,'/self-checkin/'+kiosk['public_key'],{'request_id':str(uuid.uuid4())}).status_code==410


def test_walkin_idempotency_and_concurrent_last_slot(client,clinic,test_url):
    dep,_=clinic
    kiosk=post(client,'/checkin/kiosks',{'department_id':dep['id']}).json()
    slot=publish(client,dep)
    session=client.cookies.get('queuesense_session')
    def book(_):
        with TestClient(create_app(Settings(test_url,(ORIGIN,)))) as other:
            other.cookies.set('queuesense_session',session)
            return post(other,'/appointments',{'slot_id':slot['id']}).status_code
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(book,range(4)))
    assert sorted(results)==[201,409,409,409]
    request_id=str(uuid.uuid4())
    def arrive(_):
        with TestClient(create_app(Settings(test_url,(ORIGIN,)))) as other:
            result=post(other,'/self-checkin/'+kiosk['public_key'],{'request_id':request_id})
            assert result.status_code==200,result.text
            return result.json()['patient_key']
    with ThreadPoolExecutor(max_workers=4) as pool: keys=list(pool.map(arrive,range(4)))
    assert len(set(keys))==1
    assert len(client.get('/queue/live?department='+dep['id']).json()['tokens'])==1


def test_slot_validation_and_committed_notifications(client,clinic,test_url):
    dep,_=clinic
    assert post(client,'/appointments/slots',dict(department_id=dep['id'],starts_at=(next_slot()+timedelta(minutes=1)).isoformat(),capacity=1)).status_code==422
    assert post(client,'/appointments/slots',dict(department_id=dep['id'],starts_at=(next_slot()-timedelta(days=1)).isoformat(),capacity=1)).status_code==422
    publish(client,dep)
    assert post(client,'/appointments/slots',dict(department_id=dep['id'],starts_at=next_slot().isoformat(),capacity=1)).status_code==409
    with psycopg.connect(test_url,autocommit=True) as listen:
        listen.execute('LISTEN queuesense_queue')
        token=post(client,'/queue/check-in',{'department_id':dep['id']});assert token.status_code==201
        notifications=list(listen.notifies(timeout=2,stop_after=1))
        assert notifications and notifications[0].payload==''

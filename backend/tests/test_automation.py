from datetime import datetime,timedelta,timezone
import uuid

import psycopg
from psycopg.rows import dict_row

from backend.app import Settings
from backend.automation import run_cycle,appointment_risk,congestion
from backend.tests.test_auth import client,test_url,login,ORIGIN
from backend.tests.test_product import clinic,post,patch


def booking(test_url,dep,starts,created=None):
    with psycopg.connect(test_url,row_factory=dict_row) as conn:
        slot=conn.execute('INSERT INTO appointment_slots(department_id,starts_at,capacity) VALUES(%s,%s,20) ON CONFLICT(department_id,starts_at) DO UPDATE SET capacity=20 RETURNING id',(dep['id'],starts)).fetchone()
        return conn.execute('INSERT INTO appointments(slot_id,reference,public_key,created_at) VALUES(%s,%s,%s,%s) RETURNING *',(slot['id'],'APT-'+uuid.uuid4().hex,uuid.uuid4().hex+uuid.uuid4().hex,created or datetime.now(timezone.utc))).fetchone()


def cycle(test_url,now):return run_cycle(Settings(test_url,(ORIGIN,),automation_enabled=False),now)


def test_early_congestion_includes_bookings_without_double_counting_walkins(client,clinic,test_url):
    dep,doctor=clinic;now=datetime.now(timezone.utc)
    bookings=[booking(test_url,dep,now+timedelta(minutes=10)) for _ in range(8)]
    with psycopg.connect(test_url,row_factory=dict_row) as conn:
        result=congestion(conn,dep['id'],now)
    assert result['waiting']==0 and result['recent_walkins']==0
    assert result['horizons'][0]['booked_arrivals']==8
    assert result['level'] in ('warning','critical')
    assert post(client,'/self-checkin/'+bookings[0]['public_key'],{'request_id':str(uuid.uuid4())}).status_code==200
    with psycopg.connect(test_url,row_factory=dict_row) as conn:
        arrived=congestion(conn,dep['id'])
    assert arrived['waiting']==1 and arrived['recent_walkins']==0
    assert arrived['horizons'][0]['booked_arrivals']==7
    assert patch(client,f'/staff/{doctor["id"]}/availability',{'status':'offline'}).status_code==200
    result=client.get('/planning/congestion?department_id='+dep['id']).json()[0]
    assert result['level']=='critical'
    assert all(h['estimated_wait'] is None for h in result['horizons'])
    cycle(test_url,now);cycle(test_url,now)
    messages=client.get('/notifications').json()
    assert len([m for m in messages if m['kind']=='congestion'])==1


def test_reminders_confirmation_and_private_notification_isolation(client,clinic,test_url):
    dep,doctor=clinic;now=datetime.now(timezone.utc)
    first=booking(test_url,dep,now+timedelta(minutes=40),now-timedelta(days=8))
    other=booking(test_url,dep,now+timedelta(minutes=40))
    cycle(test_url,now);cycle(test_url,now)
    assert post(client,'/self-checkin/'+first['public_key']+'/confirm').status_code==200
    assert post(client,'/self-checkin/'+first['public_key']+'/confirm').status_code==200
    assert post(client,'/self-checkin/'+first['public_key']+'/confirm',{}).status_code==200
    feed=client.get('/self-checkin/'+first['public_key']+'/notifications').json()
    assert feed['confirmed_at'] and len(feed['notifications'])==1
    notice=feed['notifications'][0]
    assert post(client,f'/self-checkin/{other["public_key"]}/notifications/{notice["id"]}/read').status_code==404
    assert post(client,f'/self-checkin/{first["public_key"]}/notifications/{notice["id"]}/read').status_code==200
    with psycopg.connect(test_url,row_factory=dict_row) as conn:
        row=conn.execute('SELECT a.*,s.starts_at FROM appointments a JOIN appointment_slots s ON s.id=a.slot_id WHERE a.id=%s',(first['id'],)).fetchone()
        assert appointment_risk(row,now)['level']=='low'
        assert conn.execute("SELECT count(*) AS n FROM audit_logs WHERE action='confirm_attendance' AND entity_id=%s",(first['id'],)).fetchone()['n']==1
    client.cookies.clear()
    assert client.get('/notifications').status_code==401
    assert client.get('/appointments/risks?day='+now.date().isoformat()).status_code==401
    assert client.get('/self-checkin/'+first['public_key']+'/notifications').status_code==200
    assert post(client,'/self-checkin/'+first['public_key']+'/confirm',{}).status_code==200
    assert client.post('/self-checkin/'+first['public_key']+'/confirm').status_code==403


def test_reminder_stages_and_expiry_never_cancel_or_duplicate(client,clinic,test_url):
    dep,doctor=clinic;now=datetime.now(timezone.utc);starts=now+timedelta(hours=3)
    booked=booking(test_url,dep,starts)
    cycle(test_url,now);cycle(test_url,starts-timedelta(minutes=50));cycle(test_url,starts-timedelta(minutes=20));cycle(test_url,starts+timedelta(minutes=31));cycle(test_url,starts+timedelta(minutes=32))
    feed=client.get('/self-checkin/'+booked['public_key']+'/notifications').json()
    assert feed['status']=='booked' and feed['attendance_outcome']=='no_show'
    assert len([n for n in feed['notifications'] if n['kind']=='appointment_reminder'])==3
    assert len([n for n in feed['notifications'] if n['kind']=='missed_arrival'])==1
    assert post(client,'/self-checkin/'+booked['public_key']+'/confirm').status_code==409
    assert post(client,'/appointments/'+str(booked['id'])+'/cancel').status_code==200
    assert any(n['kind']=='booking_cancelled' for n in client.get('/self-checkin/'+booked['public_key']+'/notifications').json()['notifications'])


def test_worker_lock_excludes_another_process_and_releases_after_commit(client,clinic,test_url):
    now=datetime.now(timezone.utc)
    with psycopg.connect(test_url) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(current_schema() || ':queuesense_automation',0))")
        assert cycle(test_url,now) is False
        assert conn.execute("SELECT count(*) FROM automation_state WHERE entity_key='worker:heartbeat'").fetchone()[0]==0
    assert cycle(test_url,now) is True


def test_status_notifications_immediate_and_wait_recalculation(client,clinic,test_url):
    dep,doctor=clinic;now=datetime.now(timezone.utc)
    first=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    second=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    path='/patient/'+second['public_key']+'/notifications'
    assert client.get(path).json()[0]['kind']=='queue_status'
    cycle(test_url,now);cycle(test_url,now)
    assert len([n for n in client.get(path).json() if n['kind']=='waiting_update'])==1
    assert patch(client,f'/staff/{doctor["id"]}/availability',{'status':'offline'}).status_code==200
    cycle(test_url,now)
    assert any('unavailable' in n['message'] for n in client.get(path).json())
    assert patch(client,f'/staff/{doctor["id"]}/availability',{'status':'available'}).status_code==200
    assert patch(client,f'/queue/{first["id"]}/status',{'status':'called','staff_id':doctor['id']}).status_code==200
    immediate=client.get('/patient/'+first['public_key']+'/notifications').json()
    called=next(n for n in immediate if 'your turn' in n['message'])
    assert post(client,path+'/'+called['id']+'/read').status_code==404
    assert post(client,'/patient/'+first['public_key']+'/notifications/'+called['id']+'/read').status_code==200
    assert all('public_key' not in n and 'token_id' not in n for n in immediate)


def test_staff_receipts_are_personal_and_risk_role_access(client,clinic,test_url):
    dep,doctor=clinic;now=datetime.now(timezone.utc)
    booking(test_url,dep,now+timedelta(minutes=20),now-timedelta(days=10))
    cycle(test_url,now)
    notice=client.get('/notifications').json()[0]
    assert post(client,'/notifications/'+notice['id']+'/read').status_code==200
    assert next(n for n in client.get('/notifications').json() if n['id']==notice['id'])['is_read']
    login(client,'manager')
    assert not next(n for n in client.get('/notifications').json() if n['id']==notice['id'])['is_read']
    assert client.get('/appointments/risks?day='+now.date().isoformat()).status_code==403
    login(client,'reception')
    assert client.get('/appointments/risks?day=bad').status_code==422
    assert client.get('/planning/congestion').status_code==200

import csv
import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

import psycopg
import pytest
from fastapi.testclient import TestClient
from backend.app import Settings,create_app
from backend.tests.test_auth import client,test_url,login,ORIGIN
from backend.product import Simulation,simulate


def post(client,path,body=None):return client.post(path,json=body,headers={'Origin':ORIGIN})
def patch(client,path,body):return client.patch(path,json=body,headers={'Origin':ORIGIN})


@pytest.fixture
def clinic(client):
    assert login(client,'admin').status_code==200
    dep=post(client,'/admin/departments',dict(code='TEST',name='Test clinic',location='Synthetic',queue_threshold=1))
    assert dep.status_code==201,dep.text
    dep=dep.json()
    users=client.get('/admin/users').json();doctor=next(u for u in users if u['email']=='doctor@staff.example.test')
    st=post(client,'/admin/staff',dict(department_id=dep['id'],display_name='Test clinician',user_id=doctor['id'])).json()
    assert patch(client,f'/staff/{st["id"]}/availability',{'status':'available'}).status_code==200
    return dep,st


def test_end_to_end_queue_analytics_public_link_and_exports(client,clinic):
    dep,st=clinic
    created=post(client,'/queue/check-in',{'department_id':dep['id']});assert created.status_code==201,created.text
    token=created.json();key=token['public_key']
    public=client.get('/patient/'+key).json();assert public['status']=='waiting' and 'id' not in public and 'synthetic_patient_id' not in public
    assert post(client,f'/staff/{st["id"]}/call-next').status_code==200
    assert patch(client,f'/staff/{st["id"]}/availability',{'status':'break'}).status_code==409
    assert patch(client,f'/queue/{token["id"]}/status',{'status':'in_service'}).status_code==200
    assert patch(client,f'/queue/{token["id"]}/status',{'status':'completed'}).status_code==200
    assert patch(client,f'/queue/{token["id"]}/status',{'status':'called','staff_id':st['id']}).status_code==409
    day=datetime.now(ZoneInfo('Asia/Colombo')).date();query=f'?start={day}&end={day}&department={dep["id"]}'
    report=client.get('/analytics/summary'+query);assert report.status_code==200,report.text
    assert report.json()['summary']['completed']==1
    assert report.json()['summary']['average_wait']>=0
    csv_result=client.get('/reports/export'+query+'&format=csv');assert csv_result.status_code==200 and 'completed' in csv_result.text
    pdf=client.get('/reports/export'+query+'&format=pdf');assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
    assert client.get('/patient/'+key).json()['status']=='completed'
    assert post(client,f'/queue/{dep["id"]}/close').status_code==200
    assert post(client,'/queue/check-in',{'department_id':dep['id']}).status_code==409
    assert any(row['action']=='completed' for row in client.get('/audit').json())


def test_server_role_boundaries_and_doctor_assignment(client,clinic):
    dep,st=clinic
    token=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    assert login(client,'manager').status_code==200
    assert post(client,'/queue/check-in',{'department_id':dep['id']}).status_code==403
    assert client.get('/admin/users').status_code==403
    assert login(client,'doctor').status_code==200
    assert client.get('/analytics/summary?start=2026-06-01&end=2026-09-01').status_code==403
    assert post(client,f'/staff/{st["id"]}/call-next').status_code==200
    assert patch(client,f'/queue/{token["id"]}/status',{'status':'no_show'}).status_code==200


def test_csv_dry_run_partial_import_duplicates_and_invalid_timestamps(client,clinic):
    day=(datetime.now(ZoneInfo('Asia/Colombo'))-timedelta(days=4)).date()
    text=f'department,token_no,status,check_in_at,called_at,service_start_at,completed_at,ended_at\nTEST,21,completed,{day}T08:00:00+05:30,{day}T08:02:00+05:30,{day}T08:03:00+05:30,{day}T08:15:00+05:30,{day}T08:15:00+05:30\nTEST,22,completed,{day}T08:00:00+05:30,{day}T07:00:00+05:30,{day}T08:03:00+05:30,{day}T08:15:00+05:30,{day}T08:15:00+05:30\n'
    preview=post(client,'/data/import',{'csv_text':text,'dry_run':True});assert preview.status_code==200,preview.text
    assert preview.json()['accepted']==1 and preview.json()['rejected']==1
    result=post(client,'/data/import',{'csv_text':text,'dry_run':False});assert result.json()['accepted']==1,result.text
    again=post(client,'/data/import',{'csv_text':text,'dry_run':False});assert again.json()['duplicates']==1 and again.json()['rejected']==1
    assert post(client,'/data/import',{'csv_text':'name,diagnosis\nJane,cold','dry_run':True}).status_code==422


def test_concurrent_token_numbers_and_staff_double_booking(client,clinic,test_url):
    dep,st=clinic
    session=client.cookies.get('queuesense_session')
    def create():
        with TestClient(create_app(Settings(test_url,(ORIGIN,)))) as other:
            other.cookies.set('queuesense_session',session)
            result=post(other,'/queue/check-in',{'department_id':dep['id']});assert result.status_code==201,result.text
            return result.json()['token_no']
    with ThreadPoolExecutor(max_workers=4) as pool:numbers=list(pool.map(lambda _:create(),range(4)))
    assert len(set(numbers))==4
    assert post(client,f'/staff/{st["id"]}/call-next').status_code==200
    assert post(client,f'/staff/{st["id"]}/call-next').status_code==409


def test_schedules_alerts_and_admin_access_updates(client,clinic):
    dep,st=clinic
    now=datetime.now(ZoneInfo('Asia/Colombo'));body={'start_at':now.isoformat(),'end_at':(now+timedelta(hours=2)).isoformat()}
    assert post(client,f'/admin/staff/{st["id"]}/schedule',body).status_code==200
    assert post(client,f'/admin/staff/{st["id"]}/schedule',body).status_code==409
    for _ in range(2):post(client,'/queue/check-in',{'department_id':dep['id']})
    assert post(client,'/alerts/refresh').status_code==200
    alerts=client.get('/alerts').json();assert any(a['alert_type']=='high_queue' and not a['resolved_at'] for a in alerts)
    assert post(client,f'/alerts/{alerts[0]["id"]}/resolve').status_code==200
    person=post(client,'/admin/users',{'email':'new@example.test','password':'Synthetic-password-2026','role':'manager'});assert person.status_code==201
    assert patch(client,'/admin/users/'+person.json()['id'],{'role':'reception','is_active':False}).status_code==200


def test_simulation_edge_cases():
    stable=simulate(Simulation(queue=10,staff=2,arrivals_per_hour=5,service_minutes=10));assert stable['stable'] and stable['clearance_minutes']>0
    unstable=simulate(Simulation(queue=10,staff=1,arrivals_per_hour=20,service_minutes=10));assert not unstable['stable'] and unstable['clearance_minutes'] is None
    assert simulate(Simulation(queue=0,staff=2,arrivals_per_hour=0,service_minutes=10))['estimated_wait']==0

from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

import psycopg
import pytest
from backend.tests.test_auth import client,test_url,login
from backend.tests.test_product import clinic,post,patch
from backend.planning import Comparison,compare


def profile(client,doctor,services=None,languages=None):
    result=patch(client,f'/admin/staff/{doctor["id"]}/profile',{'service_types':services or ['general_consultation'],'languages':languages or []})
    assert result.status_code==200,result.text


def another(client,dep,name='Second doctor'):
    row=post(client,'/admin/staff',{'department_id':dep['id'],'display_name':name}).json()
    assert patch(client,f'/staff/{row["id"]}/availability',{'status':'available'}).status_code==200
    return row


def test_matching_and_queue_enforcement(client,clinic):
    dep,doctor=clinic;other=another(client,dep)
    profile(client,doctor,['general_consultation','follow_up'],['ta'])
    profile(client,other,['general_consultation'],['en'])
    token=post(client,'/queue/check-in',{'department_id':dep['id'],'service_type':'follow_up','required_language':'ta','preferred_staff_id':doctor['id'],'continuity_required':True}).json()
    result=post(client,'/planning/doctors',{'department_id':dep['id'],'token_id':token['id']})
    assert result.status_code==200,result.text
    assert [r['id'] for r in result.json()['doctors']]==[doctor['id']]
    assert patch(client,f'/queue/{token["id"]}/status',{'status':'called','staff_id':other['id']}).status_code==409
    assert post(client,f'/staff/{other["id"]}/call-next').status_code==409
    assert post(client,f'/staff/{doctor["id"]}/call-next').status_code==200
    assert post(client,'/queue/check-in',{'department_id':dep['id'],'continuity_required':True}).status_code==422
    assert post(client,'/planning/doctors',{'department_id':dep['id'],'required_language':'si'}).json()['doctors']==[]
    assert patch(client,f'/staff/{other["id"]}/availability',{'status':'break'}).status_code==200
    result=post(client,'/planning/doctors',{'department_id':dep['id']}).json()
    assert all(r['id']!=other['id'] for r in result['doctors'])


def test_load_balancing_excludes_continuity_and_priority_and_patient_privacy(client,clinic,test_url):
    dep,doctor=clinic;other=another(client,dep)
    protected=post(client,'/queue/check-in',{'department_id':dep['id'],'preferred_staff_id':doctor['id'],'continuity_required':True}).json()
    expedited=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    ordinary=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    with psycopg.connect(test_url) as conn:conn.execute("UPDATE queue_tokens SET priority_class='expedited' WHERE id=%s",(expedited['id'],))
    result=client.get('/planning/balance?department_id='+dep['id']).json()
    assert result['overloaded'] and result['proposals']==[]
    assert patch(client,f'/queue/{expedited["id"]}/status',{'status':'cancelled'}).status_code==200
    result=client.get('/planning/balance?department_id='+dep['id']).json()
    assert result['overloaded']
    assert {r['token_id'] for r in result['proposals']}=={ordinary['id']}
    assert len({r['token_id'] for r in result['proposals']})==len(result['proposals'])
    client.cookies.clear()
    public=client.get('/patient/'+protected['public_key']+'/doctors')
    assert public.status_code==200
    assert [r['name'] for r in public.json()['doctors']]==[doctor['display_name']]
    assert 'staff_id' not in public.text and 'user_id' not in public.text and 'token_id' not in public.text
    assert client.get('/planning/balance?department_id='+dep['id']).status_code==401


def seed_history(test_url,dep,doctor):
    zone=ZoneInfo('Asia/Colombo');day=datetime.now(zone).date()+timedelta(days=1)
    with psycopg.connect(test_url) as conn:
        for week,n in [(3,0),(2,3),(1,6)]:
            past=day-timedelta(days=week*7);start=datetime.combine(past,datetime.min.time(),zone)
            session=conn.execute('INSERT INTO queue_sessions(department_id,service_date,opened_at,closed_at) VALUES(%s,%s,%s,%s) RETURNING id',(dep['id'],past,start,start+timedelta(hours=23))).fetchone()[0]
            for number in range(1,n+2):
                arrival=start+timedelta(hours=10 if number<=n else 11,minutes=number)
                conn.execute("INSERT INTO queue_tokens(session_id,department_id,staff_id,token_no,synthetic_patient_id,status,check_in_at,called_at,service_start_at,completed_at,ended_at) VALUES(%s,%s,%s,%s,'SYN-HISTORY','completed',%s,%s,%s,%s,%s)",(session,dep['id'],doctor['id'],number,arrival,arrival+timedelta(minutes=1),arrival+timedelta(minutes=2),arrival+timedelta(minutes=12),arrival+timedelta(minutes=12)))
    return day


def test_peak_forecast_zero_hour_normalization_and_staffing(client,clinic,test_url):
    dep,doctor=clinic;day=seed_history(test_url,dep,doctor)
    result=client.get(f'/planning/forecast?department_id={dep["id"]}&day={day}')
    assert result.status_code==200,result.text
    data=result.json();assert data['sufficient'] and data['sample_days']==3
    assert data['hours'][10]['expected_arrivals']==3
    assert data['hours'][10]['planning_arrivals']==pytest.approx(4.8)
    assert data['hours'][9]['expected_arrivals']==0
    assert data['service_minutes']==10
    assert data['hours'][10]['recommended_staff']==1
    assert data['peak_hours'][0]['hour']==10
    assert data['waiting']==0
    lower=client.get(f'/planning/forecast?department_id={dep["id"]}&day={day}&target_utilization=0.5').json()
    assert lower['hours'][10]['recommended_staff']>=data['hours'][10]['recommended_staff']
    assert client.get(f'/planning/forecast?department_id={dep["id"]}&day={day+timedelta(days=31)}').status_code==422


def test_insufficient_history_and_planning_permissions(client,clinic):
    dep,doctor=clinic;day=datetime.now(ZoneInfo('Asia/Colombo')).date()
    path=f'/planning/forecast?department_id={dep["id"]}&day={day}'
    data=client.get(path).json();assert not data['sufficient']
    assert all(h['expected_arrivals'] is None and h['recommended_staff'] is None for h in data['hours'])
    for role in ['reception','doctor']:
        assert login(client,role).status_code==200
        assert client.get(path).status_code==403
        assert post(client,'/planning/simulate',dict(queue=2,baseline_staff=1,scenario_staff=2,arrivals_per_hour=5,service_minutes=10)).status_code==403
        assert patch(client,f'/admin/staff/{doctor["id"]}/profile',{'service_types':['general_consultation']}).status_code==403
    assert login(client,'manager').status_code==200
    assert client.get(path).status_code==200


def test_what_if_add_remove_zero_staff_and_validation():
    added=compare(Comparison(queue=12,baseline_staff=1,scenario_staff=2,arrivals_per_hour=8,service_minutes=12))
    assert added['scenario']['estimated_wait']<added['baseline']['estimated_wait']
    assert added['scenario']['remaining_queue']<added['baseline']['remaining_queue']
    removed=compare(Comparison(queue=12,baseline_staff=1,scenario_staff=0,arrivals_per_hour=8,service_minutes=12))
    assert removed['scenario']['estimated_wait'] is None
    assert removed['scenario']['completed']==0 and removed['scenario']['remaining_queue']==20
    assert removed['wait_change'] is None
    empty=compare(Comparison(queue=0,baseline_staff=0,scenario_staff=0,arrivals_per_hour=0,service_minutes=12))
    assert empty['scenario']['stable'] and empty['scenario']['estimated_wait']==0
    from pydantic import ValidationError
    with pytest.raises(ValidationError):Comparison(queue=1,baseline_staff=1,scenario_staff=2,arrivals_per_hour=float('nan'),service_minutes=10)

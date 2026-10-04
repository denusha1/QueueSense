import csv
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg
import pytest

from backend.tests.test_auth import client,test_url,login
from backend.tests.test_product import clinic,post,patch
from backend.tests.test_experience import complete


def cohort(dep):
    day=datetime.now(ZoneInfo('Asia/Colombo')).date()
    return f'?start={day}&end={day}&department={dep["id"]}'


def test_patient_ahead_includes_active_service_and_stays_private(client,clinic):
    dep,staff=clinic
    first=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    second=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    path='/patient/'+second['public_key']
    assert client.get(path).json()['patients_ahead']==1
    assert post(client,f'/staff/{staff["id"]}/call-next').status_code==200
    assert patch(client,f'/queue/{first["id"]}/status',{'status':'in_service'}).status_code==200
    assert client.get(path).json()['patients_ahead']==1
    assert client.get(path).json()['estimated_wait']>0
    live=client.get('/queue/live').json()['tokens']
    assert next(row for row in live if row['id']==second['id'])['patients_ahead']==1
    assert patch(client,f'/queue/{first["id"]}/status',{'status':'completed'}).status_code==200
    client.cookies.clear()
    result=client.get(path).json()
    assert result['patients_ahead']==0
    assert not {'public_key','id','staff_id','session_id','synthetic_patient_id'} & result.keys()
    assert client.get('/queue/live').status_code==401


@pytest.mark.parametrize('kind',['daily','monthly','doctor','department','waiting','peak_hour','operational','visits'])
def test_specialized_reports_share_filters_and_formats(client,clinic,kind):
    dep,staff=clinic
    complete(client,dep,staff)
    path='/reports/export'+cohort(dep)+f'&report_type={kind}&staff={staff["id"]}'
    result=client.get(path+'&format=csv')
    assert result.status_code==200,result.text
    assert len(list(csv.reader(io.StringIO(result.text))))>=2
    assert 'public_key' not in result.text and 'synthetic_patient_id' not in result.text
    pdf=client.get(path+'&format=pdf')
    assert pdf.status_code==200,pdf.text
    assert pdf.content.startswith(b'%PDF')
    events=client.get('/audit?search=export_').json()
    assert any(r['details']['report_type']==kind and r['details']['staff_id']==staff['id'] for r in events)
    assert client.get(path+'&hour_from=23&hour_to=1').status_code==422


def test_observed_monitoring_latest_pre_service_and_date_filters(client,clinic,test_url):
    dep,staff=clinic
    token=complete(client,dep,staff)
    with psycopg.connect(test_url) as conn:
        times=conn.execute('SELECT check_in_at,service_start_at FROM queue_tokens WHERE id=%s',(token['id'],)).fetchone()
        begin=times[0]-timedelta(days=2)
        conn.execute("INSERT INTO model_runs(model_name,version,training_start,training_end,mae,rmse,r2) VALUES('Test','test-monitoring',%s,%s,1,1,0)",(begin,begin+timedelta(days=1)))
        for value,stamp in [(10,times[0]),(20,times[1]),(100,times[1]+timedelta(seconds=1))]:
            conn.execute("INSERT INTO predictions(token_id,predicted_wait_minutes,model_version,predicted_at) VALUES(%s,%s,'test-monitoring',%s)",(token['id'],value,stamp))
    actual=(times[1]-times[0]).total_seconds()/60
    result=client.get('/models/performance'+cohort(dep))
    assert result.status_code==200,result.text
    data=result.json()['live_monitoring']
    assert data['summary']['count']==1
    assert data['summary']['mae']==pytest.approx(abs(actual-20))
    assert data['summary']['bias']==pytest.approx(actual-20)
    assert data['samples'][0]['predicted']==20
    assert data['trends'][0]['count']==1 and data['versions'][0]['model_version']=='test-monitoring'
    assert 'token_id' not in str(data) and 'public_key' not in str(data)
    assert client.get('/models/performance?start=2026-01-01&end=2026-01-02').json()['live_monitoring']['summary']['count']==0
    assert client.get('/models/performance?start=2026-01-02&end=2026-01-01').status_code==422


def test_audit_actor_transition_filters_and_role_boundaries(client,clinic):
    dep,staff=clinic
    token=complete(client,dep,staff)
    events=client.get('/audit?entity_id='+token['id']).json()
    assert {r['action'] for r in events}=={'check_in','called','in_service','completed'}
    change=next(r for r in events if r['action']=='completed')
    assert change['actor_type']=='staff'
    assert change['details']['from_status']=='in_service' and change['details']['to_status']=='completed'
    assert client.get('/audit?offset=200').json()==[]
    assert client.get('/audit?start=2026-01-01&end=2026-01-02').json()==[]
    for role in ['doctor','reception','manager']:
        assert login(client,role).status_code==200
        assert client.get('/audit').status_code==403
        expected=200 if role=='manager' else 403
        assert client.get('/models/performance'+cohort(dep)).status_code==expected
        assert client.get('/reports/export'+cohort(dep)).status_code==expected
    client.cookies.clear()
    assert post(client,'/patient/'+token['public_key']+'/feedback',{'rating':4,'comment':'Private comment'}).status_code==201
    assert login(client,'admin').status_code==200
    public=client.get('/audit?search=submit_feedback').json()
    assert public[0]['actor_type']=='patient' and public[0]['user_id'] is None
    assert 'Private comment' not in str(public)


def test_rule_recommendations_include_evidence_and_sparse_data():
    from backend.services.insights import recommendations
    data=dict(summary={'arrivals':30},departments=[dict(name='Clinic',average_wait=45,completed=30)],heatmap=[dict(weekday=1,hour=9,arrivals=30)],workload=[],trends=[])
    result=recommendations(data)
    assert len(result)==2
    assert all(r['evidence'] and r['recommendation'] for r in result)
    data.update(departments=[],heatmap=[])
    assert recommendations(data)[0]['title']=='Continue monitoring'

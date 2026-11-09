from datetime import datetime
from zoneinfo import ZoneInfo
import uuid

import psycopg
from backend.tests.test_auth import client,test_url,login,ORIGIN
from backend.tests.test_product import clinic,post,patch


def test_priority_call_order_positions_and_authorization(client,clinic,test_url):
    dep,doctor=clinic
    standard=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    assert post(client,'/planning/doctors',{'department_id':dep['id']}).json()['doctors'][0]['expected_wait']==12
    assert post(client,'/planning/doctors',{'department_id':dep['id'],'priority_class':'expedited','priority_reason':'Clinic policy P1'}).json()['doctors'][0]['expected_wait']==0
    assert post(client,'/queue/check-in',{'department_id':dep['id'],'priority_class':'expedited'}).status_code==422
    expedited=post(client,'/queue/check-in',{'department_id':dep['id'],'priority_class':'expedited','priority_reason':'Clinic policy P1'}).json()
    next_priority=post(client,'/queue/check-in',{'department_id':dep['id'],'priority_class':'expedited','priority_reason':'Staff authorization P2'}).json()
    assert client.get('/patient/'+standard['public_key']).json()['patients_ahead']==2
    assert client.get('/patient/'+expedited['public_key']).json()['patients_ahead']==0
    live=client.get('/queue/live').json()['tokens']
    assert [r['id'] for r in live]==[expedited['id'],next_priority['id'],standard['id']]
    assert post(client,f'/staff/{doctor["id"]}/call-next').json()['id']==expedited['id']
    assert patch(client,f'/queue/{expedited["id"]}/status',{'status':'no_show'}).status_code==200
    assert post(client,f'/staff/{doctor["id"]}/call-next').json()['id']==next_priority['id']
    with psycopg.connect(test_url) as conn:
        details=conn.execute("SELECT details FROM audit_logs WHERE action='check_in' AND entity_id=%s",(expedited['id'],)).fetchone()[0]
        assert details['priority_class']=='expedited' and details['priority_reason']=='Clinic policy P1'
    login(client,'doctor')
    assert post(client,'/queue/check-in',{'department_id':dep['id'],'priority_class':'expedited','priority_reason':'Policy P1'}).status_code==403


def test_private_links_are_not_in_queue_payloads_and_require_reception_or_admin(client,clinic):
    dep,doctor=clinic
    token=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    for payload in [client.get('/queue/live').json()['tokens'],client.get('/queue/page').json()['rows']]:
        assert payload and all('public_key' not in row for row in payload)
    assert client.get(f"/queue/{token['id']}/private-link").json()=={'public_key':token['public_key']}
    assert patch(client,f"/queue/{token['id']}/status",{'status':'cancelled'}).json().get('public_key') is None
    login(client,'manager')
    assert client.get(f"/queue/{token['id']}/private-link").status_code==403
    login(client,'doctor')
    assert client.get(f"/queue/{token['id']}/private-link").status_code==403


def test_private_tracking_qr_and_public_checkin_cannot_choose_priority(client,clinic):
    dep,doctor=clinic
    token=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    key=token['public_key'];client.cookies.clear()
    qr=client.get('/patient/'+key+'/qr',params={'origin':ORIGIN})
    assert qr.status_code==200 and qr.headers['content-type'].startswith('image/svg+xml')
    assert qr.headers['cache-control']=='no-store'
    assert client.get('/patient/'+key+'/qr',params={'origin':'https://untrusted.example'}).status_code==422
    assert client.get('/patient/'+'x'*32+'/qr',params={'origin':ORIGIN}).status_code==404
    assert post(client,'/self-checkin/'+'x'*32,{'request_id':str(uuid.uuid4()),'priority_class':'expedited'}).status_code==422
    result=client.get('/patient/'+key).json()
    assert 'priority_reason' not in result and 'public_key' not in result


def test_ai_live_inference_initial_snapshot_and_actual_comparison(client,clinic,test_url,monkeypatch):
    import backend.services.prediction as prediction
    class Model:
        def predict(self,rows):return [5+row['queue_ahead']*10 for row in rows]
    monkeypatch.setattr(prediction,'artifact',lambda:{'model':Model(),'version':'test-ai'})
    dep,doctor=clinic
    first=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    second=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    assert first['prediction']['source']=='ai' and second['prediction']['minutes']==15
    assert client.get('/patient/'+second['public_key']).json()['estimated_wait']==15
    assert patch(client,f'/queue/{first["id"]}/status',{'status':'cancelled'}).status_code==200
    assert client.get('/patient/'+second['public_key']).json()['estimated_wait']==5
    assert post(client,f'/staff/{doctor["id"]}/call-next').status_code==200
    assert patch(client,f'/queue/{second["id"]}/status',{'status':'in_service'}).status_code==200
    status=client.get('/patient/'+second['public_key']).json()
    assert status['initial_prediction']==15 and status['actual_wait'] is not None
    assert status['prediction_error']==round(status['actual_wait']-15,1)
    with psycopg.connect(test_url) as conn:
        stored=conn.execute('SELECT initial_wait_minutes FROM queue_tokens WHERE id=%s',(second['id'],)).fetchone()[0]
        assert stored==15
    day=datetime.now(ZoneInfo('Asia/Colombo')).date()
    result=client.get(f'/models/performance?start={day}&end={day}&department={dep["id"]}').json()['live_monitoring']
    assert result['summary']['count']==1 and result['samples'][0]['predicted']==15


def test_priority_restrictions_and_model_failure_use_capacity_fallback(client,clinic,monkeypatch):
    import backend.services.prediction as prediction
    class Broken:
        def predict(self,rows):raise ValueError('Sensitive internal model detail')
    monkeypatch.setattr(prediction,'artifact',lambda:{'model':Broken(),'version':'broken'})
    dep,doctor=clinic
    token=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    assert token['prediction']['source']=='operational'
    assert 'Sensitive internal' not in str(token)
    priority=post(client,'/queue/check-in',{'department_id':dep['id'],'priority_class':'expedited','priority_reason':'Policy reference'}).json()
    assert priority['prediction']['source']=='operational'
    assert client.get('/patient/'+priority['public_key']).json()['estimated_wait']==0
    assert client.get('/patient/'+token['public_key']).json()['estimated_wait']==12
    assert patch(client,f'/staff/{doctor["id"]}/availability',{'status':'offline'}).status_code==200
    assert client.get('/patient/'+priority['public_key']).json()['estimated_wait'] is None
    assert post(client,'/predict/wait-time',{'department_id':dep['id']}).json()['minutes'] is None

from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from backend.app import Settings, create_app
from backend.tests.test_auth import client, test_url, login, ORIGIN
from backend.tests.test_product import clinic, post, patch


def complete(client, dep, staff):
    token = post(client, '/queue/check-in', {'department_id': dep['id']}).json()
    assert post(client, f'/staff/{staff["id"]}/call-next').status_code == 200
    assert patch(client, f'/queue/{token["id"]}/status', {'status':'in_service'}).status_code == 200
    assert patch(client, f'/queue/{token["id"]}/status', {'status':'completed'}).status_code == 200
    return token


def test_feedback_lifecycle_privacy_and_concurrent_duplicates(client, clinic, test_url):
    dep, staff = clinic
    waiting = post(client, '/queue/check-in', {'department_id': dep['id']}).json()
    path = '/patient/'+waiting['public_key']+'/feedback'
    assert client.get(path).json() == {'eligible':False, 'submitted':False}
    assert post(client,path,{'rating':5}).status_code == 409
    assert post(client,f'/staff/{staff["id"]}/call-next').status_code == 200
    assert patch(client,f'/queue/{waiting["id"]}/status',{'status':'in_service'}).status_code == 200
    assert patch(client,f'/queue/{waiting["id"]}/status',{'status':'completed'}).status_code == 200
    client.cookies.clear()
    for body in [{'rating':0}, {'rating':6}, {'rating':True}, {'rating':3,'comment':'x'*1001}, {'rating':4,'extra':'x'}]:
        assert post(client,path,body).status_code == 422
    def submit(_):
        with TestClient(create_app(Settings(test_url,(ORIGIN,)))) as public:
            return post(public,path,{'rating':4,'comment':'  Helpful staff  '}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit,range(2))) == [201,409]
    assert client.get(path).json() == {'eligible':True,'submitted':True}
    assert 'Helpful staff' not in client.get(path).text
    assert post(client,'/patient/'+'x'*43+'/feedback',{'rating':3}).status_code == 404
    assert client.post(path,json={'rating':5}).status_code == 403


def test_feedback_summary_cohort_and_access(client,clinic):
    dep,staff=clinic
    token=complete(client,dep,staff)
    assert post(client,'/patient/'+token['public_key']+'/feedback',{'rating':2,'comment':'Long wait'}).status_code==201
    day=datetime.now(ZoneInfo('Asia/Colombo')).date()
    path=f'/feedback/summary?start={day}&end={day}&department={dep["id"]}'
    result=client.get(path).json()
    assert result['summary']['responses']==1 and result['summary']['average_rating']==2
    assert result['summary']['wait_rating_correlation'] is None
    assert result['comments'][0]['comment']=='Long wait'
    assert 'public_key' not in str(result) and 'token_id' not in str(result)
    for role in ['reception','doctor']:
        assert login(client,role).status_code==200
        assert client.get(path).status_code==403
        assert client.get('/health/services').status_code==403
    assert login(client,'manager').status_code==200
    assert client.get(path).status_code==200
    assert client.get('/feedback/summary?start=2026-10-02&end=2026-10-01').status_code==422


def test_health_checks_and_security_headers(client,clinic,monkeypatch):
    import backend.services.prediction as prediction
    response=client.get('/health/services')
    assert response.status_code==200,response.text
    rows={s['service']:s for s in response.json()['services']}
    assert rows['Database']['status']=='healthy'
    assert rows['Notification service']['status']=='healthy'
    assert rows['Machine learning']['status']=='healthy'
    assert response.headers['Referrer-Policy']=='no-referrer'
    assert response.headers['X-Frame-Options']=='DENY'
    monkeypatch.setattr(prediction,'artifact',lambda:None)
    assert client.get('/health/services').json()['status']=='degraded'
    class Broken:
        def predict(self,_): raise ValueError('private sensitive model error')
    monkeypatch.setattr(prediction,'artifact',lambda:{'model':Broken()})
    response=client.get('/health/services')
    assert 'private sensitive' not in response.text
    assert response.json()['services'][-1]['status']=='unavailable'


def test_wait_rating_relationship_uses_measured_visit_wait(client, clinic, monkeypatch):
    from datetime import timedelta
    import backend.product as product
    dep, staff = clinic
    clock = [datetime.now(ZoneInfo('Asia/Colombo')).replace(hour=9,minute=0,second=0,microsecond=0)]
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)
    monkeypatch.setattr(product,'datetime',Clock)
    for minutes, rating in [(5,5),(20,3),(35,1)]:
        token=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
        clock[0]+=timedelta(minutes=minutes)
        assert post(client,f'/staff/{staff["id"]}/call-next').status_code==200
        assert patch(client,f'/queue/{token["id"]}/status',{'status':'in_service'}).status_code==200
        clock[0]+=timedelta(minutes=10)
        assert patch(client,f'/queue/{token["id"]}/status',{'status':'completed'}).status_code==200
        assert post(client,'/patient/'+token['public_key']+'/feedback',{'rating':rating}).status_code==201
    day=clock[0].date()
    result=client.get(f'/feedback/summary?start={day}&end={day}&department={dep["id"]}').json()
    assert result['summary']['responses']==3
    assert float(result['summary']['average_wait'])==20
    assert result['summary']['wait_rating_correlation']==-1
    assert [float(b['average_rating']) for b in result['bands']]==[5,3,1]

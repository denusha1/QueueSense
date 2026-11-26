"""Security and transport regression tests use isolated data and mocked providers."""
import base64,json,re,secrets,time,uuid
from datetime import datetime,timezone
import psycopg
import pytest
from backend.app import COOKIE,Settings,digest
from backend.security import encrypt,totp
from backend.delivery import run_delivery
from backend.tests.test_auth import client,test_url,login,ORIGIN,PASSWORD
from backend.tests.test_product import clinic,post

@pytest.fixture(autouse=True)
def isolated_delivery_state(test_url):
    with psycopg.connect(test_url) as conn:conn.execute('TRUNCATE notification_targets,security_attempts CASCADE')

def test_profile_sessions_and_password_rotation(client):
    assert login(client).status_code==200
    assert post(client,'/auth/profile',{'display_name':'Reception desk','language':'ta'}).status_code==200
    assert client.get('/auth/profile').json()['preferred_language']=='ta'
    assert client.get('/auth/profile').json()['display_name']=='Reception desk'
    old=client.cookies[COOKIE]
    assert post(client,'/auth/password',{'current_password':PASSWORD,'new_password':'New-secure-password-2026!'}).status_code==200
    current=client.cookies[COOKIE];assert current!=old
    sessions=client.get('/auth/sessions').json();assert len(sessions)==1 and sessions[0]['current']
    client.cookies.set(COOKIE,old);assert client.get('/auth/me').status_code==401
    client.cookies.set(COOKIE,current)
    assert post(client,'/auth/sessions/'+sessions[0]['id']+'/revoke',{}).json()['current']
    assert client.get('/auth/me').status_code==401
    assert login(client,password=PASSWORD).status_code==401
    assert login(client,password='New-secure-password-2026!').status_code==200

def test_own_session_boundary_and_demo_security(client,test_url):
    login(client,'admin');own=client.get('/auth/sessions').json()[0]['id']
    login(client,'reception');assert post(client,'/auth/sessions/'+own+'/revoke',{}).status_code==404
    assert post(client,'/auth/mfa/setup',{'password':PASSWORD}).status_code==403
    assert post(client,'/auth/demo',{'role':'admin'}).status_code==200
    assert post(client,'/auth/password',{'current_password':PASSWORD,'new_password':'New-password-2026!'}).status_code==400
    assert post(client,'/auth/mfa/setup',{'password':PASSWORD}).status_code==400

def test_mfa_required_replay_resistance_and_encrypted_secret(client,test_url,monkeypatch):
    login(client,'admin');result=post(client,'/auth/mfa/setup',{'password':PASSWORD});assert result.status_code==200
    secret=result.json()['secret'];step=int(time.time()/30)
    with psycopg.connect(test_url) as conn:assert secret not in conn.execute('SELECT secret_encrypted FROM account_mfa').fetchone()[0]
    assert post(client,'/auth/mfa/confirm',{'password':PASSWORD,'otp':totp(secret,step)}).status_code==200
    assert client.get('/auth/me').status_code==401
    assert login(client,'admin').status_code==401
    assert post(client,'/auth/login',{'email':'admin@staff.example.test','role':'admin','password':PASSWORD,'otp':totp(secret,step)}).status_code==401
    monkeypatch.setattr('backend.security.time.time',lambda:(step+1)*30+1)
    code=totp(secret,step+1)
    assert post(client,'/auth/login',{'email':'admin@staff.example.test','role':'admin','password':PASSWORD,'otp':code}).status_code==200
    assert post(client,'/auth/login',{'email':'admin@staff.example.test','role':'admin','password':PASSWORD,'otp':code}).status_code==401
    with psycopg.connect(test_url) as conn:
        details=' '.join(str(r[0]) for r in conn.execute('SELECT details FROM audit_logs').fetchall());assert secret not in details and PASSWORD not in details

def test_recovery_one_time_and_old_sessions_revoked(client,test_url,monkeypatch):
    login(client,'reception');old=client.cookies[COOKIE]
    monkeypatch.setenv('SMTP_HOST','example.test');monkeypatch.setenv('SMTP_FROM','clinic@example.test')
    messages=[];monkeypatch.setattr('backend.delivery.mail',lambda address,text:messages.append(text))
    missing=post(client,'/auth/recovery/request',{'email':'missing@example.test'}).json()
    known=post(client,'/auth/recovery/request',{'email':'reception@staff.example.test'}).json();assert missing==known
    code=re.search(r'code: ([A-Za-z0-9_-]+)',messages[0]).group(1)
    with psycopg.connect(test_url) as conn:assert conn.execute('SELECT token_hash FROM account_recovery').fetchone()[0]==digest(code)
    body={'token':code,'password':'Recovery-new-password-2026!'}
    assert post(client,'/auth/recovery/reset',body).status_code==200
    assert post(client,'/auth/recovery/reset',body).status_code==400
    client.cookies.set(COOKIE,old);assert client.get('/auth/me').status_code==401
    assert login(client,password=body['password']).status_code==200

def test_verified_contact_scope_consent_retries_and_idempotency(client,clinic,test_url,monkeypatch):
    dep,_=clinic;token=post(client,'/queue/check-in',{'department_id':dep['id']}).json();other=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    path='/patient/'+token['public_key']+'/delivery'
    assert client.get(path).status_code==200
    assert client.get('/patient/'+secrets.token_urlsafe(32)+'/delivery').status_code==404
    monkeypatch.setenv('SMTP_HOST','example.test');monkeypatch.setenv('SMTP_FROM','clinic@example.test')
    sent=[];monkeypatch.setattr('backend.delivery.send',lambda *args,**kwargs:sent.append(args))
    body={'channel':'email','destination':'synthetic@example.test','consent':False}
    assert post(client,path,body).status_code==422
    body['consent']=True;assert post(client,path,body).status_code==200
    code=re.search(r'code: (\d{6})',sent[0][2]).group(1)
    assert post(client,'/patient/'+other['public_key']+'/delivery/email/verify',{'code':code}).status_code==400
    assert post(client,path+'/email/verify',{'code':'999999' if code!='999999' else '000000'}).status_code==400
    assert post(client,path+'/email/verify',{'code':code}).status_code==200
    assert post(client,path+'/email/verify',{'code':code}).status_code==400
    targets=client.get(path).json()['targets'];assert targets[0]['verified'] and 'destination_encrypted' not in targets[0]
    with psycopg.connect(test_url) as conn:
        assert 'synthetic@example.test' not in conn.execute('SELECT destination_encrypted FROM notification_targets').fetchone()[0]
        conn.execute("INSERT INTO notifications(department_id,token_id,audience,kind,message,event_key) VALUES(%s,%s,'patient','called','Private clinic detail',%s)",(dep['id'],token['id'],uuid.uuid4().hex))
    config=Settings(test_url,(ORIGIN,),automation_enabled=False)
    def failed(*args,**kwargs):raise RuntimeError('Provider body must not be stored')
    monkeypatch.setattr('backend.delivery.send',failed);run_delivery(config)
    with psycopg.connect(test_url) as conn:
        assert conn.execute('SELECT attempts,last_error FROM notification_deliveries').fetchone()==(1,'RuntimeError')
        conn.execute('UPDATE notification_deliveries SET next_attempt=now()')
    monkeypatch.setattr('backend.delivery.send',lambda *args,**kwargs:sent.append(args));run_delivery(config);run_delivery(config)
    assert len(sent)==2 and len(sent[1])==2
    with psycopg.connect(test_url) as conn:assert conn.execute('SELECT state,attempts FROM notification_deliveries').fetchone()==('sent',2)
    assert post(client,path+'/email/disable',{}).status_code==200
    assert client.get(path).json()['targets']==[]

def test_push_rejects_untrusted_endpoints(client,monkeypatch):
    login(client);monkeypatch.setenv('VAPID_PRIVATE_KEY','configured');monkeypatch.setenv('VAPID_PUBLIC_KEY','configured');monkeypatch.setenv('VAPID_SUBJECT','mailto:clinic@example.test')
    keys={'auth':base64.urlsafe_b64encode(b'x'*16).decode(),'p256dh':base64.urlsafe_b64encode(b'x'*65).decode()}
    for endpoint in ['http://127.0.0.1/x','https://127.0.0.1/x','https://fcm.googleapis.com.evil.example/x','https://fcm.googleapis.com:8443/x']:
        assert post(client,'/delivery/targets/push',{'endpoint':endpoint,'keys':keys,'consent':True}).status_code==422
    assert post(client,'/delivery/targets/push',{'endpoint':'https://fcm.googleapis.com/example','keys':keys,'consent':True}).status_code==200
    assert client.get('/delivery/targets').json()['targets'][0]['verified']

def test_database_paging_beyond_500_and_literal_search(client,clinic,test_url):
    dep,_=clinic;token=post(client,'/queue/check-in',{'department_id':dep['id']}).json()
    with psycopg.connect(test_url) as conn:
        session=conn.execute('SELECT session_id FROM queue_tokens WHERE id=%s',(token['id'],)).fetchone()[0]
        conn.execute("INSERT INTO queue_tokens(session_id,department_id,token_no,synthetic_patient_id,check_in_at,public_key) SELECT %s,%s,n,'SYN-PAGE-'||n,now(),repeat('x',30)||n FROM generate_series(2,605) n",(session,dep['id']))
    query='/queue/page?department='+dep['id']+'&sort=token'
    result=client.get(query+'&page=61').json();assert result['total']==605 and result['page']==61 and len(result['rows'])==5 and result['rows'][0]['token_no']==601
    assert result['summary']['waiting']==605
    assert client.get(query+'&page=9999').json()['page']==61
    assert client.get(query+'&search=TEST-605').json()['total']==1
    assert client.get(query+'&search=%25').json()['total']==0
    assert client.get(query+'&page_size=51').status_code==422
    assert client.get(query+'&sort=invalid').status_code==422
    audit=client.get('/audit/page').json();assert audit['total']>=1 and len(audit['rows'])<=10
    users=client.get('/admin/users/page').json();assert users['total']==8 and all('password_hash' not in u for u in users['rows'])
    login(client,'manager');assert client.get('/audit/page').status_code==403 and client.get('/admin/users/page').status_code==403

def test_provider_adapters_use_tls_and_generic_payloads(monkeypatch):
    from backend.delivery import send,GENERIC
    monkeypatch.setenv('SMTP_HOST','smtp.example.test');monkeypatch.setenv('SMTP_FROM','clinic@example.test');monkeypatch.delenv('SMTP_SSL',raising=False);monkeypatch.delenv('SMTP_USER',raising=False)
    captured={}
    class SMTP:
        def __init__(self,host,port,timeout):captured['smtp']=(host,port,timeout)
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def starttls(self,*,context):captured['tls']=context
        def send_message(self,message):captured['email']=message.get_content()
    monkeypatch.setattr('backend.delivery.smtplib.SMTP',SMTP)
    send('email','synthetic@example.test');assert captured['tls'].check_hostname and GENERIC in captured['email']
    monkeypatch.setenv('TWILIO_ACCOUNT_SID','AC'+'0'*32);monkeypatch.setenv('TWILIO_AUTH_TOKEN','synthetic-test');monkeypatch.setenv('TWILIO_FROM','+15555550000')
    class HTTP:
        def __init__(self,timeout,follow_redirects):assert timeout==8 and not follow_redirects
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,auth,data):
            assert url.startswith('https://api.twilio.com/');captured['sms']=data['Body']
            class Result:
                def raise_for_status(self):pass
            return Result()
    monkeypatch.setattr('backend.delivery.httpx.Client',HTTP);send('sms','+15555550001');assert captured['sms']==GENERIC
    monkeypatch.setenv('VAPID_PRIVATE_KEY','synthetic-test');monkeypatch.setenv('VAPID_PUBLIC_KEY','synthetic-test');monkeypatch.setenv('VAPID_SUBJECT','mailto:clinic@example.test')
    monkeypatch.setattr('pywebpush.webpush',lambda subscription,**kwargs:captured.update(push=json.loads(kwargs['data'])))
    send('push',json.dumps({'endpoint':'https://fcm.googleapis.com/example','keys':{}}),url='/')
    assert captured['push']['body']==GENERIC and captured['push']['url']=='/'

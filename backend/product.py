"""Queue operations, analytics and administration; every write is role-checked."""
import csv
import io
import json
import math
import secrets
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, ConfigDict, model_validator
from psycopg import sql

from backend.app import connection, HASHER
from backend.services.metrics import analytics, filters, BASE

TZ = ZoneInfo('Asia/Colombo')
ROOT = Path(__file__).resolve().parents[1]
OPS = ('admin','reception','doctor')
MANAGERS = ('admin','manager')
TRANSITIONS = {'waiting': ['called','cancelled'], 'called': ['in_service','cancelled','no_show'], 'in_service': ['completed']}


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CheckIn(Input):
    department_id: uuid.UUID
    priority_class: Literal['standard','expedited']='standard'
    priority_reason: str=Field(default='',max_length=160)
    service_type: Literal['general_consultation','follow_up','document_review','accessible_consultation']='general_consultation'
    required_language: Literal['en','ta','si']|None=None
    preferred_staff_id:uuid.UUID|None=None
    continuity_required:bool=False

    @model_validator(mode='after')
    def continuity(self):
        self.priority_reason=self.priority_reason.strip()
        if self.priority_class=='expedited' and len(self.priority_reason)<3:
            raise ValueError('Record a clinic policy reference or staff authorization for expedited priority.')
        if self.continuity_required and self.preferred_staff_id is None:
            raise ValueError('Choose a doctor when continuity is required.')
        return self


class Change(Input):
    status: Literal['called','in_service','completed','cancelled','no_show']
    staff_id: uuid.UUID | None = None


class Availability(Input):
    status: Literal['available','break','offline']


class Simulation(Input):
    queue: int = Field(ge=0, le=10000)
    staff: int = Field(ge=1, le=100)
    arrivals_per_hour: float = Field(ge=0, le=10000, allow_inf_nan=False)
    service_minutes: float = Field(gt=0, le=240, allow_inf_nan=False)


def simulate(body):
    capacity = body.staff*60/body.service_minutes
    stable = capacity > body.arrivals_per_hour
    clearance = body.queue/(capacity-body.arrivals_per_hour)*60 if stable else None
    wait = body.queue*body.service_minutes/body.staff
    return dict(capacity_per_hour=round(capacity,1),clearance_minutes=round(clearance,1) if clearance is not None else None,estimated_wait=round(wait,1),congestion='high' if not stable or wait>30 else 'moderate' if wait>15 else 'low',stable=stable,assumptions='Constant arrivals and service duration; FIFO; all staff continuously available. Breaks and variability are excluded. An estimate, not a clinical recommendation.')


class DepartmentInput(Input):
    code: str = Field(pattern='^[A-Z]{2,8}$')
    name: str = Field(min_length=2,max_length=80)
    location: str = Field(min_length=1,max_length=100)
    queue_threshold: int = Field(ge=1,le=1000)


class UserInput(Input):
    email: str = Field(pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$',max_length=254)
    password: str = Field(min_length=12,max_length=128)
    role: Literal['admin','manager','doctor','reception']


class UserUpdate(Input):
    role: Literal['admin','manager','doctor','reception']
    is_active: bool


class StaffInput(Input):
    department_id: uuid.UUID
    display_name: str = Field(min_length=2,max_length=80)
    user_id: uuid.UUID | None = None


class ScheduleInput(Input):
    start_at: datetime
    end_at: datetime


class ImportInput(Input):
    csv_text: str = Field(max_length=2_000_000)
    dry_run: bool = True


def require(user, roles):
    if user['role'] not in roles:
        raise HTTPException(403,'Your account does not have permission for this action.')


def audit(conn,user,action,entity,entity_id,details=None,actor_type=None):
    from psycopg.types.json import Jsonb
    conn.execute('INSERT INTO audit_logs(user_id,action,entity_type,entity_id,actor_type,details) VALUES(%s,%s,%s,%s,%s,%s)',(user['id'] if user else None,action,entity,entity_id,actor_type or ('staff' if user else 'system'),Jsonb(details or {})))


def station(conn, staff_id, user):
    row = conn.execute('SELECT * FROM staff WHERE id=%s AND is_active FOR UPDATE',(staff_id,)).fetchone()
    if not row: raise HTTPException(404,'Active clinician not found.')
    if user['role']=='doctor' and str(row['user_id'])!=user['id']:
        raise HTTPException(403,'Doctors can only manage their assigned clinician queue.')
    return row


def service_estimate(conn,department_id):
    return float(conn.execute('SELECT coalesce(avg(service_minutes),12) AS minutes FROM (SELECT extract(epoch FROM(completed_at-service_start_at))/60 AS service_minutes FROM queue_tokens WHERE department_id=%s AND completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT 30) recent',(department_id,)).fetchone()['minutes'])


def active_staff(conn,department_id):
    return conn.execute("SELECT count(*) AS count FROM staff st LEFT JOIN LATERAL (SELECT status,changed_at FROM staff_availability WHERE staff_id=st.id ORDER BY changed_at DESC LIMIT 1) a ON true WHERE st.department_id=%s AND st.is_active AND a.status IN ('available','busy') AND (a.changed_at AT TIME ZONE 'Asia/Colombo')::date=(now() AT TIME ZONE 'Asia/Colombo')::date",(department_id,)).fetchone()['count']


def queue_snapshot(conn,department=None):
    query = """SELECT t.id,t.department_id,t.staff_id,t.token_no,t.status,t.priority_class,t.priority_reason,t.initial_wait_minutes,t.initial_prediction_version,t.check_in_at,t.called_at,t.service_start_at,t.completed_at,d.code,d.name AS department,st.display_name AS clinician
FROM queue_tokens t JOIN queue_sessions s ON s.id=t.session_id JOIN departments d ON d.id=t.department_id LEFT JOIN staff st ON st.id=t.staff_id
WHERE s.service_date=(now() AT TIME ZONE d.timezone)::date AND (%s::uuid IS NULL OR d.id=%s) ORDER BY CASE t.priority_class WHEN 'expedited' THEN 0 ELSE 1 END,t.check_in_at,t.token_no LIMIT 500"""
    rows=conn.execute(query,(department,department)).fetchall()
    from backend.services.prediction import live_predictions
    estimates={}
    for row in rows:
        dep=row['department_id']
        if dep not in estimates: estimates[dep]=live_predictions(conn,dep)
        if row['status']=='waiting':
            prediction=estimates[dep].get(str(row['id']),{})
            row['position']=prediction.get('position');row['patients_ahead']=prediction.get('patients_ahead');row['estimated_wait']=prediction.get('minutes');row['prediction_source']=prediction.get('source');row['prediction_notice']=prediction.get('reason')
        else:
            row['position']=None;row['patients_ahead']=None;row['estimated_wait']=None
        row['actual_wait']=round((row['service_start_at']-row['check_in_at']).total_seconds()/60,1) if row['service_start_at'] else None
        row['prediction_error']=round(row['actual_wait']-row['initial_wait_minutes'],1) if row['actual_wait'] is not None and row['initial_wait_minutes'] is not None else None
    return rows


def issue_token(conn,department_id,user=None,requirements=None):
    conn.execute('SELECT pg_advisory_xact_lock(72419023)')
    dep=conn.execute('SELECT * FROM departments WHERE id=%s AND is_active',(department_id,)).fetchone()
    if not dep: raise HTTPException(404,'Department unavailable.')
    requirements=requirements or {}
    preferred=requirements.get('preferred_staff_id')
    if preferred:
        doctor=conn.execute("SELECT * FROM staff WHERE id=%s AND department_id=%s AND is_active AND staff_type='doctor'",(preferred,department_id)).fetchone()
        if not doctor:raise HTTPException(422,'Choose an active doctor in this department.')
        from backend.planning import eligible
        if requirements.get('continuity_required') and not eligible(doctor,requirements):
            raise HTTPException(422,'The preferred doctor does not support the required service or language.')
    now=datetime.now(ZoneInfo(dep['timezone']))
    conn.execute('INSERT INTO queue_sessions(department_id,service_date,opened_at) VALUES(%s,%s,%s) ON CONFLICT(department_id,service_date) DO NOTHING',(dep['id'],now.date(),now.replace(hour=0,minute=0,second=0,microsecond=0)))
    session=conn.execute('SELECT * FROM queue_sessions WHERE department_id=%s AND service_date=%s FOR UPDATE',(dep['id'],now.date())).fetchone()
    if session['closed_at']: raise HTTPException(409,'Today’s session has been closed.')
    number=conn.execute('SELECT coalesce(max(token_no),0)+1 AS next FROM queue_tokens WHERE session_id=%s',(session['id'],)).fetchone()['next']
    row=conn.execute('INSERT INTO queue_tokens(session_id,department_id,token_no,synthetic_patient_id,check_in_at,public_key,service_type,required_language,preferred_staff_id,continuity_required,priority_class,priority_reason) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',(session['id'],dep['id'],number,'SYN-'+secrets.token_hex(8).upper(),now,secrets.token_urlsafe(32),requirements.get('service_type','general_consultation'),requirements.get('required_language'),preferred,requirements.get('continuity_required',False),requirements.get('priority_class','standard'),requirements.get('priority_reason',''))).fetchone()
    conn.execute("INSERT INTO service_events(token_id,department_id,event_type,event_time) VALUES(%s,%s,'check_in',%s)",(row['id'],dep['id'],now))
    audit(conn,user,'check_in','queue_token',row['id'],{'status':'waiting','department_id':str(dep['id']),'priority_class':row['priority_class'],'priority_reason':row['priority_reason']},actor_type='staff' if user else 'patient')
    row['code']=dep['code']
    from backend.services.prediction import predict_for_token
    row['prediction']=predict_for_token(conn,row)
    return row


def attach_product(app,settings,current_user):
    from backend.arrivals import attach_arrivals
    attach_arrivals(app,settings,current_user,issue_token)
    @app.get('/departments')
    def departments(user=Depends(current_user)):
        with connection(settings) as conn:
            return conn.execute('SELECT * FROM departments ORDER BY name').fetchall()

    @app.get('/staff')
    def staff(user=Depends(current_user)):
        with connection(settings) as conn:
            return conn.execute("SELECT st.*,d.name AS department,coalesce(a.status,'offline') AS availability,a.changed_at FROM staff st JOIN departments d ON d.id=st.department_id LEFT JOIN LATERAL(SELECT status,changed_at FROM staff_availability WHERE staff_id=st.id AND (changed_at AT TIME ZONE 'Asia/Colombo')::date=(now() AT TIME ZONE 'Asia/Colombo')::date ORDER BY changed_at DESC LIMIT 1)a ON true ORDER BY d.name,st.display_name").fetchall()

    @app.get('/queue/live')
    def live(department: uuid.UUID | None=None,user=Depends(current_user)):
        with connection(settings) as conn:
            rows=queue_snapshot(conn,department)
            return dict(tokens=rows,as_of=datetime.now(TZ),limit=500)

    @app.post('/queue/check-in',status_code=201)
    def checkin(body:CheckIn,user=Depends(current_user)):
        require(user,('admin','reception'))
        with connection(settings) as conn:
            return issue_token(conn,body.department_id,user,body.model_dump())

    @app.get('/queue/{token_id}/private-link')
    def private_link(token_id:uuid.UUID,user=Depends(current_user)):
        require(user,('admin','reception'))
        with connection(settings) as conn:
            row=conn.execute('SELECT public_key FROM queue_tokens WHERE id=%s',(token_id,)).fetchone()
            if not row:raise HTTPException(404,'Token not found.')
            return {'public_key':row['public_key']}

    def transition(conn,token_id,body,user):
        conn.execute('SELECT pg_advisory_xact_lock(72419023)')
        token=conn.execute('SELECT * FROM queue_tokens WHERE id=%s FOR UPDATE',(token_id,)).fetchone()
        if not token: raise HTTPException(404,'Token not found.')
        if body.status not in TRANSITIONS.get(token['status'],[]): raise HTTPException(409,'This queue transition is not allowed.')
        staff_id=body.staff_id if body.status=='called' else token['staff_id']
        if user['role']=='doctor' and staff_id is None: raise HTTPException(403,'An assigned clinician is required.')
        if staff_id:
            clinician=station(conn,staff_id,user)
            if clinician['department_id']!=token['department_id']: raise HTTPException(409,'Clinician belongs to another department.')
        if body.status=='called':
            from backend.planning import eligible
            if staff_id and not eligible(clinician,token):raise HTTPException(409,'This doctor does not match the visit’s service, language or continuity requirements.')
            if not staff_id: raise HTTPException(422,'Choose a clinician to call this token.')
            availability=conn.execute("SELECT status FROM staff_availability WHERE staff_id=%s AND (changed_at AT TIME ZONE 'Asia/Colombo')::date=(now() AT TIME ZONE 'Asia/Colombo')::date ORDER BY changed_at DESC LIMIT 1",(staff_id,)).fetchone()
            if not availability or availability['status']!='available': raise HTTPException(409,'Set this clinician to available first.')
            if conn.execute("SELECT 1 FROM queue_tokens WHERE staff_id=%s AND status IN ('called','in_service')",(staff_id,)).fetchone():raise HTTPException(409,'Clinician is serving another token.')
        now=datetime.now(TZ)
        field={'called':'called_at','in_service':'service_start_at','completed':'completed_at','cancelled':'ended_at','no_show':'ended_at'}[body.status]
        values={'status':body.status,field:now,'staff_id':staff_id}
        if body.status=='completed':values['ended_at']=now
        query=sql.SQL('UPDATE queue_tokens SET {} WHERE id=%s RETURNING *').format(sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in values))
        row=conn.execute(query,(*values.values(),token_id)).fetchone()
        event='service_start' if body.status=='in_service' else body.status
        conn.execute('INSERT INTO service_events(token_id,department_id,staff_id,event_type,event_time) VALUES(%s,%s,%s,%s,%s)',(token_id,row['department_id'],staff_id,event,now))
        if staff_id and body.status in ('called','completed','cancelled','no_show'):
            conn.execute('INSERT INTO staff_availability(staff_id,status,changed_at) VALUES(%s,%s,%s)',(staff_id,'busy' if body.status=='called' else 'available',now))
        audit(conn,user,body.status,'queue_token',token_id,{'from_status':token['status'],'to_status':body.status,'staff_id':str(staff_id) if staff_id else None})
        return {key:value for key,value in row.items() if key!='public_key'}

    @app.patch('/queue/{token_id}/status')
    def change(token_id:uuid.UUID,body:Change,user=Depends(current_user)):
        require(user,OPS)
        with connection(settings) as conn:return transition(conn,token_id,body,user)

    @app.post('/staff/{staff_id}/call-next')
    def call_next(staff_id:uuid.UUID,user=Depends(current_user)):
        require(user,OPS)
        with connection(settings) as conn:
            conn.execute('SELECT pg_advisory_xact_lock(72419023)')
            clinician=station(conn,staff_id,user)
            from backend.planning import eligible
            candidates=conn.execute("SELECT t.* FROM queue_tokens t JOIN queue_sessions s ON s.id=t.session_id WHERE t.department_id=%s AND t.status='waiting' AND s.service_date=(now() AT TIME ZONE 'Asia/Colombo')::date ORDER BY CASE t.priority_class WHEN 'expedited' THEN 0 ELSE 1 END,t.check_in_at,t.token_no FOR UPDATE OF t",(clinician['department_id'],)).fetchall()
            row=next((t for t in candidates if eligible(clinician,t)),None)
            if not row:raise HTTPException(409,'No eligible patients waiting for this doctor.')
            return transition(conn,row['id'],Change(status='called',staff_id=staff_id),user)

    @app.patch('/staff/{staff_id}/availability')
    def availability(staff_id:uuid.UUID,body:Availability,user=Depends(current_user)):
        require(user,OPS)
        with connection(settings) as conn:
            conn.execute('SELECT pg_advisory_xact_lock(72419023)');station(conn,staff_id,user)
            if conn.execute("SELECT 1 FROM queue_tokens WHERE staff_id=%s AND status IN ('called','in_service')",(staff_id,)).fetchone():raise HTTPException(409,'Finish the active token before changing availability.')
            conn.execute('INSERT INTO staff_availability(staff_id,status,changed_at) VALUES(%s,%s,now())',(staff_id,body.status))
            audit(conn,user,'availability:'+body.status,'staff',staff_id)
            return {'ok':True}

    @app.post('/queue/{department_id}/close')
    def close_session(department_id:uuid.UUID,user=Depends(current_user)):
        require(user,('admin','reception'))
        with connection(settings) as conn:
            conn.execute('SELECT pg_advisory_xact_lock(72419023)')
            row=conn.execute("SELECT id FROM queue_sessions WHERE department_id=%s AND service_date=(now() AT TIME ZONE 'Asia/Colombo')::date",(department_id,)).fetchone()
            if not row:raise HTTPException(404,'No session today.')
            if conn.execute("SELECT 1 FROM queue_tokens WHERE session_id=%s AND status IN ('waiting','called','in_service')",(row['id'],)).fetchone():raise HTTPException(409,'Complete or cancel all active tokens first.')
            conn.execute('UPDATE queue_sessions SET closed_at=coalesce(closed_at,now()) WHERE id=%s',(row['id'],));audit(conn,user,'close_session','queue_session',row['id'])
            return {'ok':True}

    public_hits=[]
    @app.get('/patient/{key}/qr')
    def tracking_qr(key:str,origin:str):
        if origin not in settings.origins:raise HTTPException(422,'Use a configured clinic URL.')
        if not 30<=len(key)<=80:raise HTTPException(404,'Token not found.')
        with connection(settings) as conn:
            if not conn.execute('SELECT 1 FROM queue_tokens WHERE public_key=%s',(key,)).fetchone():raise HTTPException(404,'Token not found.')
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics import renderSVG
        qr=QrCodeWidget(origin+'/patient/'+key,barLevel='M')
        x0,y0,x1,y1=qr.getBounds()
        drawing=Drawing(256,256,transform=[256/(x1-x0),0,0,256/(y1-y0),0,0]);drawing.add(qr)
        return Response(renderSVG.drawToString(drawing),media_type='image/svg+xml')

    @app.get('/patient/{key}')
    def patient(key:str):
        now=time.monotonic()
        public_hits[:]=[stamp for stamp in public_hits if now-stamp<60]
        if len(public_hits)>=600:raise HTTPException(429,'Please retry shortly.')
        public_hits.append(now)
        if not 30<=len(key)<=80:raise HTTPException(404,'Token not found.')
        with connection(settings) as conn:
            row=conn.execute('SELECT t.id,t.session_id,t.department_id,t.token_no,t.status,t.priority_class,t.check_in_at,t.service_start_at,t.initial_wait_minutes,t.initial_prediction_version,d.name AS department,d.code FROM queue_tokens t JOIN departments d ON d.id=t.department_id WHERE public_key=%s',(key,)).fetchone()
            if not row:raise HTTPException(404,'Token not found.')
            from backend.services.prediction import live_predictions
            prediction=live_predictions(conn,row['department_id']).get(str(row['id']),{}) if row['status']=='waiting' else {}
            actual=round((row['service_start_at']-row['check_in_at']).total_seconds()/60,1) if row['service_start_at'] else None
            return dict(token=f"{row['code']}-{row['token_no']:03}",department=row['department'],status=row['status'],priority_class=row['priority_class'],position=prediction.get('position'),patients_ahead=prediction.get('patients_ahead'),estimated_wait=prediction.get('minutes'),prediction_source=prediction.get('source'),explanation=prediction.get('explanation'),initial_prediction=row['initial_wait_minutes'],actual_wait=actual,prediction_error=round(actual-row['initial_wait_minutes'],1) if actual is not None and row['initial_wait_minutes'] is not None else None,notice=prediction.get('reason','Your private token shows recorded queue progress.'))

    @app.get('/analytics/summary')
    def summary(start:date,end:date,department:uuid.UUID|None=None,staff:uuid.UUID|None=None,weekday:int|None=Query(None,ge=1,le=7),hour_from:int=Query(0,ge=0,le=23),hour_to:int=Query(23,ge=0,le=23),user=Depends(current_user)):
        require(user,MANAGERS)
        with connection(settings) as conn:return analytics(conn,start,end,department,staff,weekday,hour_from,hour_to)

    @app.post('/simulation/staffing')
    def simulation(body:Simulation,user=Depends(current_user)):
        require(user,MANAGERS);return simulate(body)

    @app.get('/models/performance')
    def performance(start:date|None=None,end:date|None=None,department:uuid.UUID|None=None,user=Depends(current_user)):
        require(user,MANAGERS)
        path=ROOT/'ml/evaluation/results.json'
        if not path.exists():raise HTTPException(503,'Train the model before viewing evaluation results.')
        result=json.loads(path.read_text())
        with connection(settings) as conn:
            from backend.services.monitoring import monitoring
            window_end=end or datetime.now(TZ).date()
            window_start=start or window_end-timedelta(days=89)
            result['live_monitoring']=monitoring(conn,window_start,window_end,department)
            result['monitoring']=result['live_monitoring']['departments']
        return result

    @app.post('/predict/wait-time')
    def predict(body:CheckIn,user=Depends(current_user)):
        with connection(settings) as conn:
            from backend.services.prediction import current_prediction
            return current_prediction(conn,body.department_id,requirements=body.model_dump())

    @app.get('/alerts')
    def alerts(user=Depends(current_user)):
        with connection(settings) as conn:return conn.execute('SELECT a.*,d.name AS department FROM alerts a JOIN departments d ON d.id=a.department_id ORDER BY (a.resolved_at IS NULL) DESC,a.created_at DESC LIMIT 100').fetchall()

    @app.post('/alerts/refresh')
    def refresh_alerts(user=Depends(current_user)):
        require(user,MANAGERS)
        with connection(settings) as conn:
            conn.execute('SELECT pg_advisory_xact_lock(72419024)')
            for dep in conn.execute('SELECT * FROM departments WHERE is_active').fetchall():
                waiting=conn.execute("SELECT count(*) AS n FROM queue_tokens WHERE department_id=%s AND status='waiting'",(dep['id'],)).fetchone()['n']
                arrivals=conn.execute("SELECT count(*) AS n FROM queue_tokens WHERE department_id=%s AND check_in_at>now()-interval '30 minutes'",(dep['id'],)).fetchone()['n']
                recent=conn.execute("SELECT avg(extract(epoch FROM(service_start_at-check_in_at))/60) AS wait FROM queue_tokens WHERE department_id=%s AND service_start_at>now()-interval '60 minutes'",(dep['id'],)).fetchone()['wait']
                baseline=conn.execute('SELECT avg(waiting_minutes) AS wait FROM token_durations WHERE department_id=%s',(dep['id'],)).fetchone()['wait']
                error=conn.execute("SELECT count(*) AS n,avg(abs(extract(epoch FROM(t.service_start_at-t.check_in_at))/60-p.predicted_wait_minutes)) AS mae FROM predictions p JOIN queue_tokens t ON t.id=p.token_id WHERE t.department_id=%s AND t.service_start_at>now()-interval '1 day'",(dep['id'],)).fetchone()
                conditions=[('high_queue',waiting>dep['queue_threshold'],f'{waiting} waiting; threshold {dep["queue_threshold"]}.'),('capacity',arrivals>active_staff(conn,dep['id'])*30/max(service_estimate(conn,dep['id']),1),f'{arrivals} arrivals in 30 minutes exceed available service capacity.'),('delay',bool(recent and baseline and recent>max(float(baseline)*1.5,20)),f'Recent wait is above the historical baseline.'),('model_error',error['n']>=10 and float(error['mae'] or 0)>15,'Observed prediction error exceeds 15 minutes across at least 10 visits.')]
                for kind,trigger,message in conditions:
                    if trigger:conn.execute("INSERT INTO alerts(department_id,alert_type,severity,message) VALUES(%s,%s,'warning',%s) ON CONFLICT(department_id,alert_type) WHERE resolved_at IS NULL DO UPDATE SET message=EXCLUDED.message",(dep['id'],kind,message))
                    else:conn.execute('UPDATE alerts SET resolved_at=now() WHERE department_id=%s AND alert_type=%s AND resolved_at IS NULL',(dep['id'],kind))
            audit(conn,user,'refresh_alerts','system',uuid.UUID(int=0))
        return {'ok':True}

    @app.post('/alerts/{alert_id}/resolve')
    def resolve_alert(alert_id:uuid.UUID,user=Depends(current_user)):
        require(user,MANAGERS)
        with connection(settings) as conn:
            row=conn.execute('UPDATE alerts SET resolved_at=coalesce(resolved_at,now()) WHERE id=%s RETURNING id',(alert_id,)).fetchone()
            if not row:raise HTTPException(404,'Alert not found.')
            audit(conn,user,'resolve_alert','alert',alert_id)
        return {'ok':True}

    @app.get('/admin/users')
    def users(user=Depends(current_user)):
        require(user,('admin',))
        with connection(settings) as conn:return conn.execute('SELECT id,email,role,is_active,created_at FROM users ORDER BY email').fetchall()

    @app.post('/admin/users',status_code=201)
    def create_user(body:UserInput,user=Depends(current_user)):
        require(user,('admin',))
        with connection(settings) as conn:
            if conn.execute('SELECT 1 FROM users WHERE email=%s',(body.email.lower(),)).fetchone():raise HTTPException(409,'An account with this email already exists.')
            row=conn.execute('INSERT INTO users(email,password_hash,role) VALUES(%s,%s,%s) RETURNING id,email,role',(body.email.lower(),HASHER.hash(body.password),body.role)).fetchone()
            audit(conn,user,'create_user','user',row['id']);return row

    @app.patch('/admin/users/{user_id}')
    def update_user(user_id:uuid.UUID,body:UserUpdate,user=Depends(current_user)):
        require(user,('admin',))
        if str(user_id)==user['id']:raise HTTPException(409,'You cannot change your own access.')
        with connection(settings) as conn:
            row=conn.execute('UPDATE users SET role=%s,is_active=%s WHERE id=%s RETURNING id',(body.role,body.is_active,user_id)).fetchone()
            if not row:raise HTTPException(404,'User not found.')
            conn.execute('DELETE FROM auth_sessions WHERE user_id=%s',(user_id,))
            audit(conn,user,'update_access','user',user_id)
        return {'ok':True}

    @app.post('/admin/departments',status_code=201)
    def add_department(body:DepartmentInput,user=Depends(current_user)):
        require(user,('admin',))
        with connection(settings) as conn:
            if conn.execute('SELECT 1 FROM departments WHERE code=%s OR name=%s',(body.code,body.name)).fetchone():raise HTTPException(409,'Department code or name already exists.')
            row=conn.execute('INSERT INTO departments(code,name,location,queue_threshold) VALUES(%s,%s,%s,%s) RETURNING *',(body.code,body.name,body.location,body.queue_threshold)).fetchone()
            audit(conn,user,'create_department','department',row['id']);return row

    @app.patch('/admin/departments/{department_id}')
    def update_department(department_id:uuid.UUID,body:DepartmentInput,user=Depends(current_user)):
        require(user,('admin',))
        with connection(settings) as conn:
            if conn.execute('SELECT 1 FROM departments WHERE (code=%s OR name=%s) AND id<>%s',(body.code,body.name,department_id)).fetchone():raise HTTPException(409,'Department name or code already exists.')
            row=conn.execute('UPDATE departments SET code=%s,name=%s,location=%s,queue_threshold=%s WHERE id=%s RETURNING id',(body.code,body.name,body.location,body.queue_threshold,department_id)).fetchone()
            if not row:raise HTTPException(404,'Department not found.')
            audit(conn,user,'update_department','department',department_id)
        return {'ok':True}

    @app.post('/admin/staff',status_code=201)
    def add_staff(body:StaffInput,user=Depends(current_user)):
        require(user,('admin',))
        with connection(settings) as conn:
            if not conn.execute('SELECT 1 FROM departments WHERE id=%s',(body.department_id,)).fetchone():raise HTTPException(404,'Department not found.')
            if body.user_id and (not conn.execute("SELECT 1 FROM users WHERE id=%s AND role='doctor'",(body.user_id,)).fetchone() or conn.execute('SELECT 1 FROM staff WHERE user_id=%s',(body.user_id,)).fetchone()):raise HTTPException(409,'Choose an unassigned doctor account.')
            row=conn.execute("INSERT INTO staff(department_id,display_name,staff_type,user_id) VALUES(%s,%s,'doctor',%s) RETURNING *",(body.department_id,body.display_name,body.user_id)).fetchone()
            audit(conn,user,'create_staff','staff',row['id']);return row

    @app.get('/schedules')
    def schedules(start:date,end:date,user=Depends(current_user)):
        filters(start,end)
        with connection(settings) as conn:return conn.execute('SELECT sc.*,st.display_name FROM staff_schedules sc JOIN staff st ON st.id=sc.staff_id WHERE service_date BETWEEN %s AND %s ORDER BY start_at LIMIT 500',(start,end)).fetchall()

    @app.post('/admin/staff/{staff_id}/schedule')
    def schedule(staff_id:uuid.UUID,body:ScheduleInput,user=Depends(current_user)):
        require(user,('admin',))
        if not body.start_at.tzinfo or not body.end_at.tzinfo or body.end_at<=body.start_at or body.end_at-body.start_at>timedelta(hours=16):raise HTTPException(422,'Use timezone-aware dates with a positive shift up to 16 hours.')
        with connection(settings) as conn:
            station(conn,staff_id,user)
            if conn.execute("SELECT 1 FROM staff_schedules WHERE staff_id=%s AND status='scheduled' AND start_at<%s AND end_at>%s",(staff_id,body.end_at,body.start_at)).fetchone():raise HTTPException(409,'Schedule overlaps an existing shift.')
            row=conn.execute('INSERT INTO staff_schedules(staff_id,service_date,start_at,end_at) VALUES(%s,%s,%s,%s) RETURNING id',(staff_id,body.start_at.astimezone(TZ).date(),body.start_at,body.end_at)).fetchone();audit(conn,user,'schedule_staff','staff_schedule',row['id'])
        return {'ok':True}

    @app.get('/audit')
    def audit_log(search:str=Query('',max_length=100),start:date|None=None,end:date|None=None,entity_id:uuid.UUID|None=None,offset:int=Query(0,ge=0,le=1000000),user=Depends(current_user)):
        require(user,('admin',))
        if start and end:filters(start,end)
        with connection(settings) as conn:
            return conn.execute("""SELECT a.*,u.email FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id
            WHERE (a.action ILIKE %s OR coalesce(u.email,'') ILIKE %s OR a.entity_type ILIKE %s)
            AND (%s::date IS NULL OR (a.created_at AT TIME ZONE 'Asia/Colombo')::date>=%s)
            AND (%s::date IS NULL OR (a.created_at AT TIME ZONE 'Asia/Colombo')::date<=%s)
            AND (%s::uuid IS NULL OR a.entity_id=%s)
            ORDER BY a.created_at DESC,a.id DESC LIMIT 200 OFFSET %s""",('%'+search+'%',)*3+(start,start,end,end,entity_id,entity_id,offset)).fetchall()

    @app.post('/data/import')
    def import_data(body:ImportInput,user=Depends(current_user)):
        require(user,MANAGERS)
        from backend.services.importer import import_csv
        with connection(settings) as conn:
            result=import_csv(conn,body.csv_text,body.dry_run)
            if not body.dry_run:audit(conn,user,'import_csv','system',uuid.UUID(int=0))
            return result

    @app.get('/reports/export')
    def export(start:date,end:date,format:Literal['csv','pdf']='csv',report_type:Literal['visits','operational','daily','monthly','doctor','department','waiting','peak_hour']='visits',department:uuid.UUID|None=None,staff:uuid.UUID|None=None,weekday:int|None=Query(None,ge=1,le=7),hour_from:int=Query(0,ge=0,le=23),hour_to:int=Query(23,ge=0,le=23),user=Depends(current_user)):
        require(user,MANAGERS)
        from backend.services.reports import sections,render
        with connection(settings) as conn:
            tables=sections(conn,start,end,report_type,department,staff,weekday,hour_from,hour_to)
            if format=='pdf' and report_type=='visits' and len(tables[0]['rows'])>5000:
                raise HTTPException(422,'Detailed PDF exceeds 5,000 visits. Narrow the selection or use CSV.')
            cohort=f'Department={department or "all"}; doctor={staff or "all"}; weekday={weekday or "all"}; hours={hour_from}:00-{hour_to}:59'
            content,media=render(tables,format,start,end,report_type,cohort)
            audit(conn,user,'export_'+format,'report',uuid.UUID(int=0),{'report_type':report_type,'start':str(start),'end':str(end),'department_id':str(department) if department else None,'staff_id':str(staff) if staff else None,'weekday':weekday,'hour_from':hour_from,'hour_to':hour_to})
        return Response(content,media_type=media,headers={'Content-Disposition':f'attachment; filename="queuesense-{report_type}-{start}-{end}.{format}"'})

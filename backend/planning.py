"""Explainable service matching, historical demand forecasts and capacity scenarios."""
import math
import uuid
from datetime import date,datetime,timedelta
from zoneinfo import ZoneInfo
from fastapi import Depends,HTTPException,Query,Path
from pydantic import Field
from backend.app import connection
from backend.product import Input,CheckIn,require,MANAGERS,audit

TZ=ZoneInfo('Asia/Colombo')


def eligible(doctor,requirements):
    return (requirements.get('service_type','general_consultation') in doctor['service_types']
        and (not requirements.get('required_language') or requirements['required_language'] in doctor['languages'])
        and (not requirements.get('continuity_required') or str(requirements.get('preferred_staff_id'))==str(doctor['id'])))


def department(conn,dep):
    row=conn.execute('SELECT * FROM departments WHERE id=%s AND is_active',(dep,)).fetchone()
    if not row:raise HTTPException(404,'Active department not found.')
    return row


def duration(conn,dep,before=None):
    row=conn.execute("SELECT avg(minutes) AS minutes,count(*) AS samples FROM (SELECT extract(epoch FROM(completed_at-service_start_at))/60 AS minutes FROM queue_tokens WHERE department_id=%s AND completed_at<%s ORDER BY completed_at DESC LIMIT 90) visits",(dep,before or datetime.now(TZ))).fetchone()
    return max(2,min(240,float(row['minutes'] or 12))),row['samples']


def roster(conn,dep):
    return conn.execute("""SELECT st.*,coalesce(a.status,'offline') AS availability,t.service_start_at,t.called_at
    FROM staff st LEFT JOIN LATERAL(SELECT status FROM staff_availability WHERE staff_id=st.id
      AND (changed_at AT TIME ZONE 'Asia/Colombo')::date=(now() AT TIME ZONE 'Asia/Colombo')::date ORDER BY changed_at DESC LIMIT 1)a ON true
    LEFT JOIN queue_tokens t ON t.staff_id=st.id AND t.status IN ('called','in_service')
    WHERE st.department_id=%s AND st.is_active AND st.staff_type='doctor' ORDER BY st.display_name""",(dep,)).fetchall()


def waiting(conn,dep):
    return conn.execute("SELECT t.*,d.code FROM queue_tokens t JOIN queue_sessions s ON s.id=t.session_id JOIN departments d ON d.id=t.department_id WHERE t.department_id=%s AND t.status='waiting' AND s.service_date=(now() AT TIME ZONE d.timezone)::date ORDER BY CASE t.priority_class WHEN 'expedited' THEN 0 ELSE 1 END,t.check_in_at,t.token_no",(dep,)).fetchall()


def recommend_doctors(conn,dep,requirements,target=None):
    clinic=department(conn,dep);minutes,samples=duration(conn,dep)
    doctors=[d for d in roster(conn,dep) if d['availability'] in ('available','busy')]
    now=datetime.now(TZ);loads={}
    for d in doctors:
        elapsed=max(0,(now-d['service_start_at']).total_seconds()/60) if d['service_start_at'] else 0
        loads[str(d['id'])]=max(1,minutes-elapsed) if d['called_at'] else 0
    unallocated=0
    for token in waiting(conn,dep):
        if target and str(token['id'])==str(target):break
        if not target and requirements.get('priority_class')=='expedited' and token['priority_class']=='standard':break
        matching=[d for d in doctors if eligible(d,token)]
        if matching:
            chosen=min(matching,key=lambda d:(loads[str(d['id'])],str(d['id'])))
            loads[str(chosen['id'])]+=minutes
        else:unallocated+=1
    candidates=[dict(id=d['id'],name=d['display_name'],availability=d['availability'],expected_wait=round(loads[str(d['id'])],1),service_types=d['service_types'],languages=d['languages'],preferred=str(d['id'])==str(requirements.get('preferred_staff_id')),reason='Same department and configured service/language requirements match.') for d in doctors if eligible(d,requirements)]
    candidates.sort(key=lambda d:(d['expected_wait'],not d['preferred'],d['name']))
    return dict(department=clinic['name'],doctors=candidates,service_minutes=round(minutes,1),service_samples=samples,unallocated_waiting=unallocated,as_of=now,notice='Approximate earliest service after compatible expedited visits, then standard visits in arrival order. Busy doctors include estimated remaining service. Service profiles must be verified by clinic staff; this does not assess medical suitability.')


def quantile(values,q):
    values=sorted(values);position=(len(values)-1)*q;lo=math.floor(position);hi=math.ceil(position)
    return values[lo]+(values[hi]-values[lo])*(position-lo)


def forecast(conn,dep,day,weeks=8,target_utilization=.8,clearance_minutes=60):
    clinic=department(conn,dep)
    today=datetime.now(TZ).date()
    if day<today or day>today+timedelta(days=30):raise HTTPException(422,'Choose today or a day within the next 30 days.')
    anchor=conn.execute('SELECT max(service_date) AS day FROM queue_sessions WHERE department_id=%s AND closed_at IS NOT NULL AND service_date<%s',(dep,day)).fetchone()['day']
    sessions=[];counts={}
    if anchor:
        sessions=conn.execute('SELECT service_date FROM queue_sessions WHERE department_id=%s AND closed_at IS NOT NULL AND service_date BETWEEN %s AND %s AND extract(isodow FROM service_date)=%s ORDER BY service_date',(dep,anchor-timedelta(days=weeks*7-1),anchor,day.isoweekday())).fetchall()
        counts={(r['service_date'],r['hour']):r['n'] for r in conn.execute("SELECT s.service_date,extract(hour FROM t.check_in_at AT TIME ZONE d.timezone)::int AS hour,count(*) AS n FROM queue_tokens t JOIN queue_sessions s ON s.id=t.session_id JOIN departments d ON d.id=t.department_id WHERE t.department_id=%s AND s.closed_at IS NOT NULL AND s.service_date BETWEEN %s AND %s GROUP BY 1,2",(dep,anchor-timedelta(days=weeks*7-1),anchor)).fetchall()}
    minutes,samples=duration(conn,dep,datetime.combine(day,datetime.min.time(),TZ))
    queued=len(waiting(conn,dep)) if day==today else 0
    on_shift=sum(d['availability'] in ('available','busy') for d in roster(conn,dep))
    sufficient=len(sessions)>=3;hours=[]
    for hour in range(24):
        values=[counts.get((r['service_date'],hour),0) for r in sessions]
        mean=sum(values)/len(values) if sufficient else None
        upper=quantile(values,.8) if sufficient else None
        backlog=queued if day==today and hour==datetime.now(TZ).hour else 0
        needed=math.ceil(round((upper*minutes/60+backlog*minutes/clearance_minutes)/target_utilization,10)) if upper is not None else None
        hours.append(dict(hour=hour,expected_arrivals=round(mean,1) if mean is not None else None,planning_arrivals=round(upper,1) if upper is not None else None,recommended_staff=needed,backlog=backlog))
    cutoff=quantile([h['expected_arrivals'] for h in hours],.75) if sufficient else None
    peaks=[h for h in hours if h['expected_arrivals'] is not None and h['expected_arrivals']>0 and h['expected_arrivals']>=cutoff]
    return dict(department=clinic['name'],day=day,hours=hours,peak_hours=sorted(peaks,key=lambda h:-h['expected_arrivals'])[:5],sample_days=len(sessions),history_age_days=(day-anchor).days if anchor else None,history_start=sessions[0]['service_date'] if sessions else None,history_end=sessions[-1]['service_date'] if sessions else None,sufficient=sufficient,service_minutes=round(minutes,1),service_samples=samples,current_staff=on_shift,waiting=queued,target_utilization=target_utilization,notice='Weekday/hour historical mean and 80th percentile across closed operating sessions, including zero-arrival hours. At least 3 comparable days are required. Staffing uses planning demand, service duration and a utilization buffer; current-hour backlog is spread across the selected clearance period. Current staffing is a live snapshot, not future roster coverage. Forecasts are estimates; clinic minimum staffing and skill mix still apply.')


class DoctorRequest(CheckIn):
    token_id:uuid.UUID|None=None


class Profile(Input):
    service_types:list[str]=Field(min_length=1,max_length=4)
    languages:list[str]=Field(default_factory=list,max_length=3)


class Comparison(Input):
    queue:int=Field(ge=0,le=10000)
    baseline_staff:int=Field(ge=0,le=100)
    scenario_staff:int=Field(ge=0,le=100)
    arrivals_per_hour:float=Field(ge=0,le=10000,allow_inf_nan=False)
    service_minutes:float=Field(ge=2,le=240,allow_inf_nan=False)
    horizon_minutes:int=Field(default=60,ge=15,le=480)


def compare(body):
    def scenario(staff):
        capacity=staff*60/body.service_minutes
        incoming=body.arrivals_per_hour*body.horizon_minutes/60
        completed=min(body.queue+incoming,capacity*body.horizon_minutes/60)
        remaining=max(0,body.queue+incoming-completed)
        net=capacity-body.arrivals_per_hour
        return dict(staff=staff,capacity_per_hour=round(capacity,1),estimated_wait=round(body.queue*body.service_minutes/staff,1) if staff else (0 if body.queue==0 and not incoming else None),completed=round(completed,1),remaining_queue=round(remaining,1),clearance_minutes=round(body.queue/net*60,1) if net>0 else (0 if not body.queue and not incoming else None),stable=net>0 or (capacity==0 and body.arrivals_per_hour==0 and body.queue==0))
    base,change=scenario(body.baseline_staff),scenario(body.scenario_staff)
    return dict(baseline=base,scenario=change,wait_change=round(change['estimated_wait']-base['estimated_wait'],1) if base['estimated_wait'] is not None and change['estimated_wait'] is not None else None,horizon_minutes=body.horizon_minutes,assumptions='Deterministic shared FIFO queue, constant arrivals and service duration, interchangeable eligible clinicians, no breaks or variability. Fractional completions represent expected throughput. This simulation does not change live queues or staffing.')


def attach_planning(app,settings,current_user):
    @app.post('/planning/doctors')
    def doctors(body:DoctorRequest,user=Depends(current_user)):
        with connection(settings) as conn:
            requirements=body.model_dump();target=body.token_id
            if target:
                requirements=conn.execute('SELECT * FROM queue_tokens WHERE id=%s AND department_id=%s AND status=\'waiting\'',(target,body.department_id)).fetchone()
                if not requirements:raise HTTPException(404,'Waiting token not found in this department.')
            return recommend_doctors(conn,body.department_id,requirements,target)

    @app.get('/patient/{key}/doctors')
    def patient_doctors(key:str=Path(pattern=r'^[A-Za-z0-9_-]{30,80}$')):
        with connection(settings) as conn:
            token=conn.execute('SELECT * FROM queue_tokens WHERE public_key=%s',(key,)).fetchone()
            if not token:raise HTTPException(404,'Token not found.')
            if token['status']!='waiting':return dict(doctors=[],notice='Doctor options are shown while you are waiting.')
            result=recommend_doctors(conn,token['department_id'],token,token['id'])
            return dict(doctors=[dict(name=d['name'],availability=d['availability'],expected_wait=d['expected_wait']) for d in result['doctors']],notice='Ask reception about these available options. Estimates and service matching require staff review.')

    @app.get('/planning/balance')
    def balance(department_id:uuid.UUID,user=Depends(current_user)):
        with connection(settings) as conn:
            clinic=department(conn,department_id);tokens=waiting(conn,department_id);doctors=roster(conn,department_id)
            overloaded=len(tokens)>clinic['queue_threshold'];proposals=[]
            available=[d for d in doctors if d['availability']=='available' and d['called_at'] is None]
            for d in available:
                token=next((t for t in tokens if eligible(d,t)),None)
                if overloaded and token and token['priority_class']=='standard' and not token['continuity_required'] and token['staff_id'] is None:
                    proposals.append(dict(token_id=token['id'],token=f"{clinic['code']}-{token['token_no']:03}",doctor_id=d['id'],doctor=d['display_name'],expected_wait=0,reason='Standard waiting visit; same department; service/language compatible; no required doctor continuity. Review patient consent and clinic eligibility before calling.'))
                    tokens=[t for t in tokens if t['id']!=token['id']]
            return dict(overloaded=overloaded,waiting=len(waiting(conn,department_id)),threshold=clinic['queue_threshold'],proposals=proposals,notice='Suggestions use idle eligible doctors in this department’s shared queue. No cross-department transfers or automatic reassignment. Required continuity and non-standard priority visits are excluded.')

    @app.get('/planning/forecast')
    def demand(department_id:uuid.UUID,day:date,weeks:int=Query(8,ge=4,le=26),target_utilization:float=Query(.8,ge=.5,le=.95),clearance_minutes:int=Query(60,ge=15,le=240),user=Depends(current_user)):
        require(user,MANAGERS)
        with connection(settings) as conn:return forecast(conn,department_id,day,weeks,target_utilization,clearance_minutes)

    @app.post('/planning/simulate')
    def what_if(body:Comparison,user=Depends(current_user)):
        require(user,MANAGERS);return compare(body)

    @app.patch('/admin/staff/{staff_id}/profile')
    def profile(staff_id:uuid.UUID,body:Profile,user=Depends(current_user)):
        require(user,('admin',))
        if not set(body.service_types)<= {'general_consultation','follow_up','document_review','accessible_consultation'} or not set(body.languages)<= {'en','ta','si'}:raise HTTPException(422,'Choose supported services and languages.')
        with connection(settings) as conn:
            row=conn.execute("UPDATE staff SET service_types=%s,languages=%s WHERE id=%s AND is_active AND staff_type='doctor' RETURNING id",(body.service_types,body.languages,staff_id)).fetchone()
            if not row:raise HTTPException(404,'Active doctor not found.')
            audit(conn,user,'update_service_profile','staff',staff_id,body.model_dump())
        return {'ok':True}

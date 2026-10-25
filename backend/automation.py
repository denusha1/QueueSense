"""Explainable operational warnings, in-app automation and opt-in delivery."""
import asyncio
import logging
import math
import uuid
from contextlib import asynccontextmanager
from datetime import datetime,timedelta,timezone

from fastapi import Depends,HTTPException
from psycopg.types.json import Jsonb

from backend.app import connection
from backend.product import require
from backend.planning import department,duration,roster,waiting,eligible

LOG=logging.getLogger('queuesense.automation')


def congestion(conn,dep,now=None):
    now=now or datetime.now(timezone.utc)
    clinic=department(conn,dep);minutes,samples=duration(conn,dep)
    doctors=[d for d in roster(conn,dep) if d['availability'] in ('available','busy')]
    tokens=waiting(conn,dep);blocked=sum(not any(eligible(d,t) for d in doctors) for t in tokens)
    arrivals=conn.execute("SELECT count(*) AS n FROM queue_tokens t WHERE department_id=%s AND check_in_at BETWEEN %s AND %s AND NOT EXISTS(SELECT 1 FROM appointments a WHERE a.token_id=t.id)",(dep,now-timedelta(minutes=30),now)).fetchone()['n']
    busy=sum(max(1,minutes-max(0,(now-d['service_start_at']).total_seconds()/60)) if d['service_start_at'] else minutes for d in doctors if d['called_at'])
    horizons=[]
    for horizon in (15,30,60):
        booked=conn.execute("SELECT count(*) AS n FROM appointments a JOIN appointment_slots s ON s.id=a.slot_id WHERE s.department_id=%s AND a.status='booked' AND a.attendance_outcome IS NULL AND s.starts_at BETWEEN %s AND %s",(dep,now-timedelta(minutes=30),now+timedelta(minutes=horizon))).fetchone()['n']
        demand=arrivals*horizon/30+booked
        capacity=max(0,(len(doctors)*horizon-busy)/minutes)
        projected=max(0,len(tokens)+demand-capacity)
        wait=round(projected*minutes/len(doctors),1) if doctors else None
        level='critical' if (not doctors and len(tokens)+demand>0) or projected>clinic['queue_threshold']*2 else 'warning' if projected>clinic['queue_threshold'] or (wait is not None and wait>=30) or blocked else 'normal'
        horizons.append(dict(minutes=horizon,booked_arrivals=booked,expected_walkins=round(arrivals*horizon/30,1),service_capacity=round(capacity,1),projected_queue=round(projected,1),estimated_wait=wait,level=level))
    level=max((h['level'] for h in horizons),key=lambda v:['normal','warning','critical'].index(v))
    return dict(department_id=dep,department=clinic['name'],waiting=len(tokens),active_doctors=len(doctors),unmatched_waiting=blocked,service_minutes=round(minutes,1),service_samples=samples,recent_walkins=arrivals,level=level,horizons=horizons,as_of=now,action='Review compatible clinician coverage and upcoming arrivals.' if level!='normal' else 'Continue monitoring.',notice='Capacity projection uses current available/busy doctors, estimated remaining service, the last 30 minutes of walk-ins and all upcoming bookings. Bookings are not discounted by no-show risk. Assumes current demand and staffing continue; averages cannot guarantee individual service times. Unmatched patients require staff review.')


def appointment_risk(row,now=None):
    now=now or datetime.now(timezone.utc)
    if row['status']!='booked' or row.get('attendance_outcome'):
        return dict(level='closed',score=None,reasons=['Arrival recorded, cancelled or check-in window ended.'])
    until=(row['starts_at']-now).total_seconds()/60
    lead=(row['starts_at']-row['created_at']).total_seconds()/86400
    score=0;reasons=[]
    if not row.get('confirmed_at'):
        score+=1;reasons.append('Attendance has not been confirmed through the private booking link.')
        if until<=60:score+=1;reasons.append('Appointment starts within one hour or has already started.')
    if lead>=7:score+=1;reasons.append('Booking was made at least seven days ahead.')
    if until<0:score+=1;reasons.append('Scheduled arrival time has passed without check-in.')
    if row.get('confirmed_at'):reasons.append('Patient confirmed attendance; this does not guarantee arrival.')
    return dict(level='high' if score>=3 else 'medium' if score>=2 else 'low',score=score,reasons=reasons,notice='Explainable booking-risk score, not a calibrated probability or a trained patient-history model. No clinical or demographic data used. Never cancels or overbooks an appointment.')


def send(conn,dep,audience,kind,message,key,token=None,appointment=None,now=None):
    conn.execute('INSERT INTO notifications(department_id,audience,kind,message,event_key,token_id,appointment_id,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(event_key) DO NOTHING',(dep,audience,kind,message,key,token,appointment,now or datetime.now(timezone.utc)))


def changed(conn,key,payload):
    old=conn.execute('SELECT payload,revision FROM automation_state WHERE entity_key=%s',(key,)).fetchone()
    if old and old['payload']==payload:return None
    version=old['revision']+1 if old else 1
    conn.execute('INSERT INTO automation_state(entity_key,payload,revision) VALUES(%s,%s,%s) ON CONFLICT(entity_key) DO UPDATE SET payload=EXCLUDED.payload,revision=EXCLUDED.revision,updated_at=now()',(key,Jsonb(payload),version))
    return version


def run_cycle(settings,now=None):
    now=now or datetime.now(timezone.utc)
    with connection(settings) as conn:
        conn.execute("SET LOCAL statement_timeout='20000ms'")
        if not conn.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(current_schema() || ':queuesense_automation',0)) AS acquired").fetchone()['acquired']:return False
        # The arrival window has ended. Record an observed outcome; never cancel a booking based on risk.
        expired=conn.execute("UPDATE appointments a SET attendance_outcome='no_show',outcome_at=%s FROM appointment_slots s WHERE a.slot_id=s.id AND a.status='booked' AND a.attendance_outcome IS NULL AND s.starts_at<%s RETURNING a.id,s.department_id",(now,now-timedelta(minutes=30))).fetchall()
        for row in expired:
            conn.execute("INSERT INTO audit_logs(action,entity_type,entity_id,actor_type,details) VALUES('appointment_window_expired','appointment',%s,'system',%s)",(row['id'],Jsonb({'outcome':'no_show','reason':'No check-in before the 30-minute grace window ended.'})))
            send(conn,row['department_id'],'appointment','missed_arrival','Your check-in window has ended. Please contact reception to arrange another visit.','missed:'+str(row['id']),appointment=row['id'],now=now)
        bookings=conn.execute("SELECT a.*,s.department_id,s.starts_at FROM appointments a JOIN appointment_slots s ON s.id=a.slot_id WHERE a.status='booked' AND a.attendance_outcome IS NULL AND s.starts_at BETWEEN %s AND %s",(now-timedelta(minutes=30),now+timedelta(hours=24))).fetchall()
        for row in bookings:
            until=(row['starts_at']-now).total_seconds()/60
            # On restart send the most relevant reminder, rather than replaying all expired stages.
            stage='arrival' if until<=30 else 'one_hour' if until<=60 else 'one_day'
            message={'arrival':'Your check-in window is open. Check in only when you arrive at the clinic.','one_hour':'Your appointment starts within one hour. Please confirm attendance or contact reception if plans change.','one_day':'Your appointment is within 24 hours. Please confirm attendance through this private page.'}[stage]
            send(conn,row['department_id'],'appointment','appointment_reminder',message,f'reminder:{row["id"]}:{stage}',appointment=row['id'],now=now)
            risk=appointment_risk(row,now)
            if risk['level']=='high':send(conn,row['department_id'],'staff','no_show_risk',f'Appointment {row["reference"]} has high booking risk. Review attendance confirmation; do not cancel based on this estimate.',f'risk:{row["id"]}:high',now=now)
        for dep in conn.execute('SELECT id FROM departments WHERE is_active').fetchall():
            prediction=congestion(conn,dep['id'],now)
            rev=changed(conn,'congestion:'+str(dep['id']),{'level':prediction['level']})
            if rev and prediction['level']!='normal':
                send(conn,dep['id'],'staff','congestion',f'{prediction["department"]}: {prediction["level"]} congestion risk within 60 minutes. {prediction["action"]}',f'congestion:{dep["id"]}:{rev}',now=now)
            from backend.services.prediction import live_predictions
            estimates=live_predictions(conn,dep['id'],now)
            for token in waiting(conn,dep['id']):
                estimate=estimates.get(str(token['id']),{}).get('minutes')
                bucket=math.ceil(estimate/5)*5 if estimate is not None else None
                version=changed(conn,'wait:'+str(token['id']),{'wait':bucket,'delay':prediction['level']!='normal'})
                if version:
                    msg=f'Updated estimated wait: about {estimate} minutes.' if estimate is not None else 'Waiting estimate unavailable while clinician coverage is unavailable. Contact reception for guidance.'
                    if prediction['level']!='normal':msg+=' The department may experience delays.'
                    send(conn,dep['id'],'patient','waiting_update',msg,f'wait:{token["id"]}:{version}',token=token['id'],now=now)
        changed(conn,'worker:heartbeat',{'last_success':now.isoformat()})
    return True


@asynccontextmanager
async def lifespan(app):
    settings=app.state.automation_settings
    try:
        from backend.services.prediction import artifact,tree_explainer
        stored=artifact()
        if stored:await asyncio.to_thread(tree_explainer,stored['version'])
    except Exception as exc:LOG.warning('SHAP explainer warmup unavailable (%s); estimates remain available.',type(exc).__name__)
    async def worker():
        while True:
            try:
                await asyncio.to_thread(run_cycle,settings)
                from backend.delivery import run_delivery
                await asyncio.to_thread(run_delivery,settings)
            except Exception as exc:LOG.error('Automation cycle failed (%s).',type(exc).__name__)
            await asyncio.sleep(30)
    task=asyncio.create_task(worker()) if settings.automation_enabled else None
    try:yield
    finally:
        if task:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass


def attach_automation(app,settings,current_user):
    app.state.automation_settings=settings

    @app.get('/planning/congestion')
    def warnings(department_id:uuid.UUID|None=None,user=Depends(current_user)):
        with connection(settings) as conn:
            deps=[department(conn,department_id)] if department_id else conn.execute('SELECT id FROM departments WHERE is_active ORDER BY name').fetchall()
            return [congestion(conn,d['id']) for d in deps]

    @app.get('/appointments/risks')
    def risks(day:str,user=Depends(current_user)):
        require(user,('reception','admin'))
        from datetime import date
        try:selected=date.fromisoformat(day)
        except ValueError:raise HTTPException(422,'Choose a valid appointment date.')
        with connection(settings) as conn:
            rows=conn.execute("SELECT a.id,a.reference,a.status,a.confirmed_at,a.attendance_outcome,a.created_at,s.starts_at FROM appointments a JOIN appointment_slots s ON s.id=a.slot_id WHERE (s.starts_at AT TIME ZONE 'Asia/Colombo')::date=%s ORDER BY s.starts_at",(selected,)).fetchall()
            for row in rows:row['risk']=appointment_risk(row)
            return rows

    def private_owner(conn,key,scope,lock=False):
        if not 30<=len(key)<=80:raise HTTPException(404,'Private link not found.')
        query='SELECT id FROM queue_tokens WHERE public_key=%s' if scope=='patient' else "SELECT a.id,a.status,a.confirmed_at,a.attendance_outcome,s.starts_at FROM appointments a JOIN appointment_slots s ON s.id=a.slot_id WHERE a.public_key=%s"
        row=conn.execute(query+(' FOR UPDATE OF a' if lock and scope=='appointment' else ''),(key,)).fetchone()
        if not row:raise HTTPException(404,'Private link not found.')
        return row

    def feed(conn,scope,owner):
        column='token_id' if scope=='patient' else 'appointment_id'
        return conn.execute(f'SELECT id,kind,message,created_at,private_read_at IS NOT NULL AS is_read FROM notifications WHERE {column}=%s AND audience=%s ORDER BY created_at DESC,id LIMIT 50',(owner,scope)).fetchall()

    @app.get('/notifications')
    def staff_feed(user=Depends(current_user)):
        with connection(settings) as conn:
            return conn.execute("SELECT n.id,n.kind,n.message,n.created_at,d.name AS department,r.read_at IS NOT NULL AS is_read FROM notifications n JOIN departments d ON d.id=n.department_id LEFT JOIN notification_reads r ON r.notification_id=n.id AND r.user_id=%s WHERE n.audience='staff' ORDER BY n.created_at DESC,n.id LIMIT 50",(user['id'],)).fetchall()

    @app.post('/notifications/{notification_id}/read')
    def staff_read(notification_id:uuid.UUID,user=Depends(current_user)):
        with connection(settings) as conn:
            row=conn.execute("SELECT id FROM notifications WHERE id=%s AND audience='staff'",(notification_id,)).fetchone()
            if not row:raise HTTPException(404,'Notification not found.')
            conn.execute('INSERT INTO notification_reads(notification_id,user_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(notification_id,user['id']))
        return {'ok':True}

    @app.get('/patient/{key}/notifications')
    def patient_feed(key:str):
        with connection(settings) as conn:return feed(conn,'patient',private_owner(conn,key,'patient')['id'])

    @app.get('/self-checkin/{key}/notifications')
    def booking_feed(key:str):
        with connection(settings) as conn:
            row=private_owner(conn,key,'appointment')
            return dict(confirmed_at=row['confirmed_at'],status=row['status'],attendance_outcome=row['attendance_outcome'],notifications=feed(conn,'appointment',row['id']))

    @app.post('/self-checkin/{key}/confirm')
    def confirm(key:str):
        with connection(settings) as conn:
            row=private_owner(conn,key,'appointment',True)
            if row['status']!='booked' or row['attendance_outcome'] or row['starts_at']<datetime.now(timezone.utc)-timedelta(minutes=30):raise HTTPException(409,'This booking is no longer open. Please contact reception.')
            conn.execute('UPDATE appointments SET confirmed_at=coalesce(confirmed_at,now()) WHERE id=%s',(row['id'],))
            if not row['confirmed_at']:
                conn.execute("INSERT INTO audit_logs(action,entity_type,entity_id,actor_type) VALUES('confirm_attendance','appointment',%s,'patient')",(row['id'],))
        return {'ok':True}

    def private_read(conn,key,scope,notification_id):
        owner=private_owner(conn,key,scope)['id'];column='token_id' if scope=='patient' else 'appointment_id'
        row=conn.execute(f'UPDATE notifications SET private_read_at=coalesce(private_read_at,now()) WHERE id=%s AND {column}=%s AND audience=%s RETURNING id',(notification_id,owner,scope)).fetchone()
        if not row:raise HTTPException(404,'Notification not found.')
        return {'ok':True}

    @app.post('/patient/{key}/notifications/{notification_id}/read')
    def patient_read(key:str,notification_id:uuid.UUID):
        with connection(settings) as conn:return private_read(conn,key,'patient',notification_id)

    @app.post('/self-checkin/{key}/notifications/{notification_id}/read')
    def booking_read(key:str,notification_id:uuid.UUID):
        with connection(settings) as conn:return private_read(conn,key,'appointment',notification_id)

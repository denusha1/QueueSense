"""Bounded table transport with database filtering and stable page ordering."""
import uuid
from datetime import date,datetime
from typing import Literal
from fastapi import Depends,Query
from backend.app import connection
from backend.product import require,filters,TZ

def pattern(value):return '%'+value.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
def metadata(rows,total,page,size):return dict(rows=rows,total=total,page=page,page_size=size,pages=max(1,(total+size-1)//size))
def decorate(conn,rows):
    from backend.services.prediction import live_predictions
    estimates={}
    for row in rows:
        if row['status']=='waiting':
            dep=row['department_id']
            if dep not in estimates:estimates[dep]=live_predictions(conn,dep)
            prediction=estimates[dep].get(str(row['id']),{})
            row.update(position=prediction.get('position'),patients_ahead=prediction.get('patients_ahead'),estimated_wait=prediction.get('minutes'),prediction_source=prediction.get('source'),prediction_notice=prediction.get('reason'))
        else:row.update(position=None,patients_ahead=None,estimated_wait=None)
        row['actual_wait']=round((row['service_start_at']-row['check_in_at']).total_seconds()/60,1) if row['service_start_at'] else None
        row['prediction_error']=round(row['actual_wait']-row['initial_wait_minutes'],1) if row['actual_wait'] is not None and row['initial_wait_minutes'] is not None else None
    return rows

def attach_table_pages(app,settings,current_user):
    @app.get('/queue/page')
    def queue_page(department:uuid.UUID|None=None,search:str=Query('',max_length=100),status:Literal['all','waiting','called','in_service','completed','cancelled','no_show']='all',sort:Literal['arrival','token','wait']='arrival',page:int=Query(1,ge=1,le=100000),page_size:int=Query(10,ge=1,le=50),user=Depends(current_user)):
        joins=' FROM queue_tokens t JOIN queue_sessions s ON s.id=t.session_id JOIN departments d ON d.id=t.department_id LEFT JOIN staff st ON st.id=t.staff_id '
        base="s.service_date=(now() AT TIME ZONE d.timezone)::date AND (%s::uuid IS NULL OR d.id=%s)"
        where=base+" AND (%s='all' OR t.status=%s) AND (d.code||'-'||lpad(t.token_no::text,greatest(3,length(t.token_no::text)),'0') ILIKE %s OR d.name ILIKE %s)"
        args=(department,department,status,status,pattern(search),pattern(search))
        fields='SELECT t.id,t.department_id,t.staff_id,t.token_no,t.status,t.priority_class,t.priority_reason,t.initial_wait_minutes,t.initial_prediction_version,t.check_in_at,t.called_at,t.service_start_at,t.completed_at,t.public_key,d.code,d.name AS department,st.display_name AS clinician'
        order="CASE t.priority_class WHEN 'expedited' THEN 0 ELSE 1 END,t.check_in_at,t.token_no,t.id" if sort!='token' else 'd.code,t.token_no,t.id'
        with connection(settings) as conn:
            total=conn.execute('SELECT count(*) AS n'+joins+' WHERE '+where,args).fetchone()['n'];page=min(page,max(1,(total+page_size-1)//page_size))
            summary={r['status']:r['n'] for r in conn.execute('SELECT t.status,count(*) AS n'+joins+' WHERE '+base+' GROUP BY t.status',(department,department)).fetchall()}
            if user['role']=='doctor':
                for r in conn.execute('SELECT t.status,count(*) AS n'+joins+' WHERE '+base+" AND st.user_id=%s AND t.status IN ('called','in_service') GROUP BY t.status",(department,department,user['id'])).fetchall():summary['my_'+r['status']]=r['n']
            if sort=='wait':
                # Live estimates require the active queue working set; historical completed rows aren't predicted.
                all_rows=decorate(conn,conn.execute(fields+joins+' WHERE '+where+' ORDER BY '+order,args).fetchall());all_rows.sort(key=lambda r:-(r['estimated_wait'] if r['estimated_wait'] is not None else -1));rows=all_rows[(page-1)*page_size:page*page_size]
            else:rows=decorate(conn,conn.execute(fields+joins+' WHERE '+where+' ORDER BY '+order+' LIMIT %s OFFSET %s',args+(page_size,(page-1)*page_size)).fetchall())
            result=metadata(rows,total,page,page_size);result.update(summary=summary,department_total=sum(summary.get(s,0) for s in ('waiting','called','in_service','completed','cancelled','no_show')),as_of=datetime.now(TZ))
            return result
    @app.get('/audit/page')
    def audit_page(search:str=Query('',max_length=100),start:date|None=None,end:date|None=None,entity_id:uuid.UUID|None=None,page:int=Query(1,ge=1,le=100000),page_size:int=Query(10,ge=1,le=50),user=Depends(current_user)):
        require(user,('admin',))
        if start and end:filters(start,end)
        joins=' FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id '
        where="(a.action ILIKE %s OR coalesce(u.email,'') ILIKE %s OR a.entity_type ILIKE %s) AND (%s::date IS NULL OR (a.created_at AT TIME ZONE 'Asia/Colombo')::date>=%s) AND (%s::date IS NULL OR (a.created_at AT TIME ZONE 'Asia/Colombo')::date<=%s) AND (%s::uuid IS NULL OR a.entity_id=%s)"
        args=(pattern(search),)*3+(start,start,end,end,entity_id,entity_id)
        with connection(settings) as conn:
            total=conn.execute('SELECT count(*) AS n'+joins+' WHERE '+where,args).fetchone()['n'];page=min(page,max(1,(total+page_size-1)//page_size))
            rows=conn.execute('SELECT a.*,u.email'+joins+' WHERE '+where+' ORDER BY a.created_at DESC,a.id DESC LIMIT %s OFFSET %s',args+(page_size,(page-1)*page_size)).fetchall()
            return metadata(rows,total,page,page_size)
    @app.get('/admin/users/page')
    def users_page(search:str=Query('',max_length=100),page:int=Query(1,ge=1,le=100000),page_size:int=Query(10,ge=1,le=50),user=Depends(current_user)):
        require(user,('admin',));args=(pattern(search),)
        with connection(settings) as conn:
            total=conn.execute('SELECT count(*) AS n FROM users WHERE email ILIKE %s',args).fetchone()['n'];page=min(page,max(1,(total+page_size-1)//page_size))
            rows=conn.execute('SELECT id,email,role,is_active,display_name FROM users WHERE email ILIKE %s ORDER BY email,id LIMIT %s OFFSET %s',args+(page_size,(page-1)*page_size)).fetchall()
            return metadata(rows,total,page,page_size)

    @app.get('/admin/doctor-options')
    def doctor_options(user=Depends(current_user)):
        require(user,('admin',))
        with connection(settings) as conn:
            return conn.execute("SELECT id,email,role FROM users u WHERE u.role='doctor' AND u.is_active AND NOT EXISTS(SELECT 1 FROM staff s WHERE s.user_id=u.id) ORDER BY email LIMIT 200").fetchall()

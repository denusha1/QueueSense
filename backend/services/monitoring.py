"""Evaluate the latest pre-service prediction per visit, without patient identifiers."""
from backend.services.metrics import filters, WAIT


def monitoring(conn,start,end,department=None):
    where,args=filters(start,end,department)
    base=f''' FROM queue_tokens t JOIN queue_sessions s ON s.id=t.session_id
    JOIN departments d ON d.id=t.department_id JOIN LATERAL (
      SELECT predicted_wait_minutes,model_version FROM (
        SELECT predicted_wait_minutes,model_version,predicted_at,id FROM predictions WHERE token_id=t.id
        UNION ALL SELECT t.initial_wait_minutes,t.initial_prediction_version,t.initial_prediction_at,t.id
          WHERE t.initial_wait_minutes IS NOT NULL
      ) candidates WHERE predicted_at<=t.service_start_at ORDER BY predicted_at DESC,id DESC LIMIT 1
    ) p ON true WHERE t.service_start_at IS NOT NULL AND {where}'''
    error=f'({WAIT}-p.predicted_wait_minutes)'
    metrics=f'count(*) AS count,avg(abs({error})) AS mae,sqrt(avg(power({error},2))) AS rmse,avg({error}) AS bias'
    summary=conn.execute('SELECT '+metrics+base,args).fetchone()
    departments=conn.execute('SELECT d.name AS department,'+metrics+base+' GROUP BY d.name ORDER BY d.name',args).fetchall()
    trends=conn.execute('SELECT s.service_date AS date,'+metrics+base+' GROUP BY s.service_date ORDER BY s.service_date',args).fetchall()
    versions=conn.execute('SELECT p.model_version,'+metrics+base+' GROUP BY p.model_version ORDER BY p.model_version',args).fetchall()
    samples=conn.execute(f'SELECT s.service_date AS date,d.name AS department,p.model_version,p.predicted_wait_minutes AS predicted,{WAIT} AS actual,{error} AS error'+base+' ORDER BY t.service_start_at DESC LIMIT 200',args).fetchall()
    return dict(summary=summary,departments=departments,trends=trends,versions=versions,samples=samples,start=start,end=end,definition='Arrival-date cohort. Latest prediction recorded no later than service start per visit. Error = actual minus predicted minutes; positive bias means underestimation. Unserved visits are excluded. Recent comparisons are limited to 200 visits.')

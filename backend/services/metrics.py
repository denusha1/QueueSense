from datetime import date
from fastapi import HTTPException


def filters(start, end, department=None, staff=None, weekday=None, hour_from=0, hour_to=23):
    if end < start or (end-start).days > 366 or hour_to < hour_from:
        raise HTTPException(422, 'Choose an ordered date range up to 366 days and valid hour range.')
    clauses = ["s.service_date BETWEEN %s AND %s", "extract(hour FROM t.check_in_at AT TIME ZONE d.timezone) BETWEEN %s AND %s"]
    values = [start, end, hour_from, hour_to]
    if department:
        clauses.append('t.department_id=%s'); values.append(department)
    if staff:
        clauses.append('t.staff_id=%s'); values.append(staff)
    if weekday is not None:
        clauses.append('extract(isodow FROM s.service_date)=%s'); values.append(weekday)
    return ' AND '.join(clauses), values


BASE = ''' FROM queue_tokens t JOIN queue_sessions s ON s.id=t.session_id
JOIN departments d ON d.id=t.department_id LEFT JOIN staff st ON st.id=t.staff_id WHERE '''
WAIT = 'extract(epoch FROM (t.service_start_at-t.check_in_at))/60.0'
SERVICE = 'extract(epoch FROM (t.completed_at-t.service_start_at))/60.0'


def analytics(conn, start, end, department=None, staff=None, weekday=None, hour_from=0, hour_to=23):
    where, args = filters(start,end,department,staff,weekday,hour_from,hour_to)
    aggregates = f'''count(*) AS arrivals, count(*) FILTER(WHERE t.status='completed') AS completed,
count(*) FILTER(WHERE t.status='waiting') AS waiting, count(*) FILTER(WHERE t.status='cancelled') AS cancelled,
count(*) FILTER(WHERE t.status='no_show') AS no_shows, avg({WAIT}) AS average_wait,
percentile_cont(.5) WITHIN GROUP(ORDER BY {WAIT}) AS median_wait,
percentile_cont(.9) WITHIN GROUP(ORDER BY {WAIT}) AS p90_wait, avg({SERVICE}) AS average_service,
100.0*count(*) FILTER(WHERE t.status='cancelled' AND s.closed_at IS NOT NULL)/nullif(count(*) FILTER(WHERE s.closed_at IS NOT NULL),0) AS cancellation_rate,
100.0*count(*) FILTER(WHERE t.status='no_show' AND s.closed_at IS NOT NULL)/nullif(count(*) FILTER(WHERE s.closed_at IS NOT NULL),0) AS no_show_rate'''
    summary = conn.execute('SELECT '+aggregates+BASE+where,args).fetchone()
    departments = conn.execute('SELECT d.name, d.code, '+aggregates+BASE+where+' GROUP BY d.name,d.code ORDER BY average_wait DESC NULLS LAST',args).fetchall()
    trends = conn.execute('SELECT s.service_date AS date, '+aggregates+BASE+where+' GROUP BY s.service_date ORDER BY s.service_date',args).fetchall()
    heatmap = conn.execute(f'SELECT extract(isodow FROM s.service_date)::int AS weekday, extract(hour FROM t.check_in_at AT TIME ZONE d.timezone)::int AS hour, count(*) AS arrivals, avg({WAIT}) AS wait'+BASE+where+' GROUP BY 1,2 ORDER BY 1,2',args).fetchall()
    workload = conn.execute(f"SELECT st.id,st.display_name AS name, count(*) FILTER(WHERE t.status='completed') AS completed, coalesce(sum({SERVICE}),0) AS busy_minutes, avg({WAIT}) AS average_wait"+BASE+where+' AND st.id IS NOT NULL GROUP BY st.id,st.display_name ORDER BY completed DESC',args).fetchall()
    for row in workload:
        scheduled = conn.execute("SELECT coalesce(sum(extract(epoch FROM (least(end_at,(service_date + %s * interval '1 hour') AT TIME ZONE 'Asia/Colombo')-greatest(start_at,(service_date + %s * interval '1 hour') AT TIME ZONE 'Asia/Colombo')))/60) FILTER(WHERE least(end_at,(service_date + %s * interval '1 hour') AT TIME ZONE 'Asia/Colombo')>greatest(start_at,(service_date + %s * interval '1 hour') AT TIME ZONE 'Asia/Colombo')),0) AS minutes FROM staff_schedules WHERE staff_id=%s AND status='scheduled' AND service_date BETWEEN %s AND %s AND (%s::int IS NULL OR extract(isodow FROM service_date)=%s)", (hour_to+1,hour_from,hour_to+1,hour_from,row['id'],start,end,weekday,weekday)).fetchone()['minutes']
        row['scheduled_minutes'] = scheduled
        # Cohort workload may include service spilling outside the selected arrival hours.
        row['utilization_proxy'] = round(float(row['busy_minutes'])/float(scheduled)*100,1) if scheduled else None
    distribution = conn.execute(f"SELECT floor(({WAIT})/10)*10 AS minutes,count(*) AS count"+BASE+where+' AND t.service_start_at IS NOT NULL GROUP BY 1 ORDER BY 1',args).fetchall()
    # Completion throughput is explicitly grouped by completion hour for the arrival cohort.
    hourly = conn.execute("SELECT extract(hour FROM t.check_in_at AT TIME ZONE d.timezone)::int AS hour,count(*) AS arrivals"+BASE+where+' GROUP BY 1 ORDER BY 1',args).fetchall()
    completions = conn.execute("SELECT extract(hour FROM t.completed_at AT TIME ZONE d.timezone)::int AS hour,count(*) AS completed"+BASE+where+" AND t.status='completed' GROUP BY 1 ORDER BY 1",args).fetchall()
    return dict(summary=summary,departments=departments,trends=trends,heatmap=heatmap,workload=workload,distribution=distribution,hourly=hourly,completions=completions,definition='Arrival-date cohort. Wait = service start − check-in. Finalized rates use closed sessions only. Workload is a cohort proxy; service may spill beyond selected arrival hours.')

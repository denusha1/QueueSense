"""Consistent tabular report sections rendered to either CSV or paginated PDF."""
import csv
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle
from backend.services.metrics import analytics, BASE, WAIT, SERVICE, filters
from fastapi import HTTPException


def sections(conn,start,end,kind,department=None,staff=None,weekday=None,hour_from=0,hour_to=23):
    args=(start,end,department,staff,weekday,hour_from,hour_to)
    report=analytics(conn,*args)
    def table(title,columns,rows):return dict(title=title,columns=columns,rows=rows)
    if kind=='visits':
        where,values=filters(*args)
        rows=conn.execute(f'SELECT d.code AS department,st.display_name AS doctor,t.token_no AS token,t.status,t.check_in_at,t.service_start_at,t.completed_at,{WAIT} AS waiting_minutes,{SERVICE} AS service_minutes'+BASE+where+' ORDER BY t.check_in_at LIMIT 50001',values).fetchall()
        if len(rows)>50000:raise HTTPException(422,'Export exceeds 50,000 rows. Narrow the date range.')
        return [table('Visit details',[('department','Department'),('doctor','Doctor'),('token','Token'),('status','Status'),('check_in_at','Check-in'),('service_start_at','Service start'),('completed_at','Completed'),('waiting_minutes','Wait min'),('service_minutes','Service min')],rows)]
    daily=[('date','Day'),('arrivals','Arrivals'),('completed','Completed'),('average_wait','Mean wait'),('p90_wait','P90 wait')]
    dept=[('name','Department'),('arrivals','Arrivals'),('completed','Completed'),('average_wait','Mean wait'),('p90_wait','P90 wait')]
    doctor=[('name','Doctor'),('completed','Completed'),('average_wait','Mean wait'),('busy_minutes','Service min'),('scheduled_minutes','Scheduled min'),('utilization_proxy','Utilization %')]
    peaks=[('weekday','Weekday (Mon=1)'),('hour','Hour'),('arrivals','Arrivals'),('wait','Mean wait')]
    tables={'daily':table('Daily performance',daily,report['trends']),'department':table('Department comparison',dept,report['departments']),'doctor':table('Doctor workload',doctor,report['workload']),'waiting':table('Waiting-time distribution',[('minutes','Band start min'),('count','Visits')],report['distribution']),'peak_hour':table('Peak arrival hours',peaks,report['heatmap'])}
    monthly={}
    for row in report['trends']:
        month=row['date'].strftime('%Y-%m')
        value=monthly.setdefault(month,dict(month=month,arrivals=0,completed=0))
        value['arrivals']+=row['arrivals'];value['completed']+=row['completed']
    # Count all measured waits, including service in progress, for a correctly weighted monthly mean.
    where,values=filters(*args)
    for row in conn.execute(f"SELECT to_char(s.service_date,'YYYY-MM') AS month,avg({WAIT}) AS average_wait"+BASE+where+' GROUP BY 1 ORDER BY 1',values).fetchall():monthly[row['month']]['average_wait']=row['average_wait']
    tables['monthly']=table('Monthly performance',[('month','Month'),('arrivals','Arrivals'),('completed','Completed'),('average_wait','Mean wait')],list(monthly.values()))
    if kind=='operational':
        summary=table('Summary',[('metric','Metric'),('value','Value')],[dict(metric=k,value=v) for k,v in report['summary'].items()])
        return [summary,*tables.values()]
    return [tables[kind]]


def display(value):
    if value is None:return 'N/A'
    if isinstance(value,(float,int)):return str(round(value,2))
    return str(value)


def render(tables,format,start,end,kind,cohort):
    if format=='csv':
        stream=io.StringIO();writer=csv.writer(stream)
        # Prevent spreadsheet formulas from text fields such as clinician display names.
        def cell(value):
            text=display(value)
            return "'"+text if isinstance(value,str) and text.lstrip().startswith(('=','+','-','@')) else text
        for i,section in enumerate(tables):
            if len(tables)>1:
                if i:writer.writerow([])
                writer.writerow([section['title']])
            writer.writerow([key for key,_ in section['columns']])
            for row in section['rows']:writer.writerow([cell(row.get(key)) for key,_ in section['columns']])
        return stream.getvalue(),'text/csv'
    stream=io.BytesIO();styles=getSampleStyleSheet()
    doc=SimpleDocTemplate(stream,pagesize=landscape(A4),rightMargin=30,leftMargin=30,topMargin=30,bottomMargin=35,title='QueueSense operational report')
    story=[Paragraph('QueueSense | '+escape(kind.replace('_',' ').title())+' report',styles['Title']),Paragraph(escape(f'Synthetic operational data | {start} to {end} | {cohort}'),styles['Normal']),Paragraph('Arrival-date cohort. Wait = service start minus check-in. Workload is a cohort proxy. Unavailable measurements are N/A.',styles['Normal']),Spacer(1,14)]
    width=landscape(A4)[0]-60
    for section in tables:
        story.extend([Paragraph(escape(section['title']),styles['Heading2']),Spacer(1,6)])
        columns=section['columns']
        rows=[[Paragraph(escape(label),styles['Normal']) for _,label in columns]]+[[Paragraph(escape(display(row.get(key))),styles['Normal']) for key,_ in columns] for row in section['rows']]
        if len(rows)==1:story.append(Paragraph('No records in this selection.',styles['Normal']));continue
        table=LongTable(rows,colWidths=[width/len(columns)]*len(columns),repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dceee6')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,colors.lightgrey),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.extend([table,Spacer(1,14)])
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.drawRightString(landscape(A4)[0]-30,18,f'QueueSense | Page {doc.page}')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return stream.getvalue(),'application/pdf'

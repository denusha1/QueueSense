"""Bounded CSV staging with row errors, deterministic duplicate keys and savepoints."""
import csv
import hashlib
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException

TZ=ZoneInfo('Asia/Colombo')
REQUIRED=['department','token_no','status','check_in_at','called_at','service_start_at','completed_at','ended_at']


def import_csv(conn,text,dry_run):
    try:
        reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
        if not reader.fieldnames or set(reader.fieldnames)!=set(REQUIRED):
            raise HTTPException(422,'CSV columns must be exactly: '+', '.join(REQUIRED))
        rows=[]
        for row in reader:
            if len(rows)>=5000:raise HTTPException(422,'Import at most 5,000 rows per file.')
            rows.append(row)
    except csv.Error as exc:raise HTTPException(422,'Malformed CSV file.') from exc
    if not rows:raise HTTPException(422,'CSV contains no data rows.')
    conn.execute('SELECT pg_advisory_xact_lock(72419023)')
    departments={d['code']:d['id'] for d in conn.execute('SELECT id,code FROM departments').fetchall()}
    seen=set();accepted=duplicates=0;errors=[];warnings=[]
    # Outer savepoint supports a real, identical database dry run without persisted changes.
    conn.execute('SAVEPOINT import_preview')
    for index,row in enumerate(rows,2):
        conn.execute('SAVEPOINT import_row')
        try:
            if None in row or any(value is None for value in row.values()):raise ValueError('Column count differs from header.')
            dep=departments.get(row['department'].strip().upper())
            if not dep:raise ValueError('Unknown department code.')
            number=int(row['token_no'])
            if number<1:raise ValueError('Token number must be positive.')
            stamps={key:datetime.fromisoformat(row[key]) if row[key].strip() else None for key in REQUIRED[3:]}
            if not stamps['check_in_at'] or any(value and value.tzinfo is None for value in stamps.values()):raise ValueError('Arrival is required; timestamps must include timezone offsets.')
            arrival=stamps['check_in_at'];day=arrival.astimezone(TZ).date()
            if day>=datetime.now(TZ).date():raise ValueError('Historical imports must precede today.')
            status=row['status'].strip()
            if status not in ('completed','cancelled','no_show'):raise ValueError('Historical rows must be completed, cancelled or no_show.')
            canonical=f'{dep}:{day}:{number}'
            key=hashlib.sha256(canonical.encode()).hexdigest()
            if key in seen or conn.execute('SELECT 1 FROM queue_tokens WHERE import_key=%s',(key,)).fetchone():duplicates+=1;continue
            existing=conn.execute('SELECT id,closed_at FROM queue_sessions WHERE department_id=%s AND service_date=%s',(dep,day)).fetchone()
            if existing and conn.execute('SELECT 1 FROM queue_tokens WHERE session_id=%s AND token_no=%s',(existing['id'],number)).fetchone():duplicates+=1;continue
            last=max(v for v in stamps.values() if v)
            if not existing:
                existing=conn.execute('INSERT INTO queue_sessions(department_id,service_date,opened_at,closed_at) VALUES(%s,%s,%s,%s) RETURNING id,closed_at',(dep,day,datetime.combine(day,datetime.min.time(),TZ),last)).fetchone()
            else:conn.execute('UPDATE queue_sessions SET closed_at=greatest(closed_at,%s) WHERE id=%s',(last,existing['id']))
            clinician=None
            if status in ('completed','no_show') or stamps['called_at']:
                st=conn.execute('SELECT id FROM staff WHERE department_id=%s ORDER BY id LIMIT 1',(dep,)).fetchone()
                if not st:raise ValueError('Department needs a demo clinician before importing service records.')
                clinician=st['id']
            token=conn.execute('INSERT INTO queue_tokens(session_id,department_id,staff_id,token_no,synthetic_patient_id,status,check_in_at,called_at,service_start_at,completed_at,ended_at,import_key) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',(existing['id'],dep,clinician,number,'SYN-IMPORT-'+key[:12].upper(),status,*stamps.values(),key)).fetchone()
            event_map={'check_in_at':'check_in','called_at':'called','service_start_at':'service_start','completed_at':'completed'}
            if status!='completed':event_map['ended_at']=status
            for field,event in event_map.items():
                if stamps[field]:conn.execute('INSERT INTO service_events(token_id,department_id,staff_id,event_type,event_time) VALUES(%s,%s,%s,%s,%s)',(token['id'],dep,None if event=='check_in' else clinician,event,stamps[field]))
            if last-arrival>timedelta(hours=4):warnings.append({'row':index,'message':'Duration exceeds four hours; retained for review.'})
            seen.add(key);accepted+=1
        except Exception as exc:
            conn.execute('ROLLBACK TO SAVEPOINT import_row')
            message=str(exc) if isinstance(exc,(ValueError,TypeError)) else 'Invalid state, timestamp chronology, session or database reference.'
            errors.append({'row':index,'message':message[:200]})
        finally:conn.execute('RELEASE SAVEPOINT import_row')
    if dry_run:conn.execute('ROLLBACK TO SAVEPOINT import_preview')
    conn.execute('RELEASE SAVEPOINT import_preview')
    return dict(dry_run=dry_run,total=len(rows),accepted=accepted,rejected=len(errors),duplicates=duplicates,errors=errors[:100],warnings=warnings[:100],note='Accepted rows can be imported; invalid rows are quarantined in this error summary. Synthetic service records are assigned to the first department demo clinician. No identifying fields are accepted.')

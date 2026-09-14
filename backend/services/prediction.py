from functools import lru_cache
from datetime import datetime
from pathlib import Path
import joblib
from zoneinfo import ZoneInfo
from fastapi import HTTPException

ROOT=Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def artifact():
    path=ROOT/'ml/artifacts/wait_model.joblib'
    return joblib.load(path) if path.exists() else None


def current_prediction(conn,department_id,at=None,exclude=None):
    from backend.product import active_staff, service_estimate
    if not conn.execute('SELECT 1 FROM departments WHERE id=%s',(department_id,)).fetchone():raise HTTPException(404,'Department not found.')
    now=at or datetime.now(ZoneInfo('Asia/Colombo'))
    ahead=conn.execute("SELECT count(*) AS n FROM queue_tokens WHERE department_id=%s AND status IN ('waiting','called') AND (%s::uuid IS NULL OR id<>%s)",(department_id,exclude,exclude)).fetchone()['n']
    arrivals=conn.execute("SELECT count(*) AS n FROM queue_tokens WHERE department_id=%s AND check_in_at<%s AND check_in_at> %s - interval '30 minutes'",(department_id,now,now)).fetchone()['n']
    count=active_staff(conn,department_id)
    duration=service_estimate(conn,department_id)
    data=dict(department=str(department_id),queue_ahead=ahead,active_staff=count,recent_service=duration,arrivals_30m=arrivals,hour=now.hour,weekday=now.weekday())
    stored=artifact()
    if not count:return dict(minutes=None,model_version=stored['version'] if stored else 'operational-baseline',reason='No clinicians available. Waiting time cannot be estimated.')
    value=float(stored['model'].predict([data])[0]) if stored and stored['model'] is not None else ahead*duration/count
    return dict(minutes=round(max(0,value),1),model_version=stored['version'] if stored else 'operational-baseline',reason='Estimate based on synthetic historical operations; not a guarantee.')


def predict_for_token(conn,token):
    result=current_prediction(conn,token['department_id'],token['check_in_at'],token['id'])
    if result['minutes'] is not None and conn.execute('SELECT 1 FROM model_runs WHERE version=%s',(result['model_version'],)).fetchone():
        conn.execute('INSERT INTO predictions(token_id,predicted_wait_minutes,model_version,predicted_at) VALUES(%s,%s,%s,%s)',(token['id'],result['minutes'],result['model_version'],token['check_in_at']))
    return result

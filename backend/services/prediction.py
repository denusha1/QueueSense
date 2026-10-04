"""Batch live inference with priority-aware, compatible-capacity fallbacks."""
import logging
import math
from functools import lru_cache
from datetime import datetime
from pathlib import Path
import joblib
from zoneinfo import ZoneInfo
from fastapi import HTTPException

ROOT=Path(__file__).resolve().parents[2]
LOG=logging.getLogger('queuesense.prediction')
BASELINE='operational-baseline'


@lru_cache(maxsize=1)
def artifact():
    path=ROOT/'ml/artifacts/wait_model.joblib'
    return joblib.load(path) if path.exists() else None


def live_predictions(conn,department_id,at=None,prospective=None):
    from backend.planning import roster,eligible
    from backend.product import service_estimate
    dep=conn.execute('SELECT * FROM departments WHERE id=%s AND is_active',(department_id,)).fetchone()
    if not dep:raise HTTPException(404,'Department not found.')
    now=(at or datetime.now(ZoneInfo(dep['timezone']))).astimezone(ZoneInfo(dep['timezone']))
    tokens=conn.execute("""SELECT t.* FROM queue_tokens t JOIN queue_sessions s ON s.id=t.session_id
      WHERE t.department_id=%s AND t.status='waiting' AND s.service_date=%s AND t.check_in_at<=%s
      ORDER BY CASE t.priority_class WHEN 'expedited' THEN 0 ELSE 1 END,t.check_in_at,t.token_no""",(department_id,now.date(),now)).fetchall()
    if prospective is not None:
        tokens.append(dict({'id':'prospective','check_in_at':now,'token_no':2147483647,'priority_class':'standard','service_type':'general_consultation','required_language':None,'continuity_required':False},**prospective))
        tokens.sort(key=lambda t:(t['priority_class']!='expedited',t['check_in_at'],t['token_no']))
    doctors=[d for d in roster(conn,department_id) if d['availability'] in ('available','busy')]
    minutes=max(2,min(240,service_estimate(conn,department_id)))
    loads={str(d['id']):max(1,minutes-max(0,(now-d['service_start_at']).total_seconds()/60)) if d['service_start_at'] else minutes if d['called_at'] else 0 for d in doctors}
    active=conn.execute("SELECT count(*) AS n FROM queue_tokens t JOIN queue_sessions s ON s.id=t.session_id WHERE t.department_id=%s AND s.service_date=%s AND t.status IN ('called','in_service')",(department_id,now.date())).fetchone()['n']
    arrivals=conn.execute("SELECT count(*) AS n FROM queue_tokens WHERE department_id=%s AND check_in_at BETWEEN %s-interval '30 minutes' AND %s",(department_id,now,now)).fetchone()['n']
    constrained=any(t['priority_class']!='standard' or t['service_type']!='general_consultation' or t['required_language'] or t['continuity_required'] for t in tokens)
    results={};features=[];targets=[]
    for index,token in enumerate(tokens):
        matching=[d for d in doctors if eligible(d,token)]
        baseline=min((loads[str(d['id'])] for d in matching),default=None)
        reason='Capacity estimate respects priority and configured clinician requirements.' if constrained else 'Operational capacity estimate; model unavailable.'
        results[str(token['id'])]=dict(minutes=round(baseline,1) if baseline is not None else None,model_version=BASELINE,source='operational',reason=reason if baseline is not None else 'No compatible clinicians available. Waiting time cannot be estimated.',position=index+active+1,patients_ahead=index+active)
        if matching:
            chosen=min(matching,key=lambda d:(loads[str(d['id'])],str(d['id'])))
            loads[str(chosen['id'])]+=minutes
            if not constrained:
                # Training features count patients who have not started service; active service is reflected in remaining capacity.
                features.append(dict(department=str(department_id),queue_ahead=index+sum(bool(d['called_at']) and not d['service_start_at'] for d in doctors),active_staff=len(doctors),recent_service=minutes,arrivals_30m=max(0,arrivals-1),hour=now.hour,weekday=now.weekday()))
                targets.append((str(token['id']),baseline))
    if features:
        try:
            stored=artifact()
            if stored and stored.get('model') is not None:
                values=stored['model'].predict(features)
                if len(values)!=len(targets) or any(not math.isfinite(float(v)) for v in values):raise ValueError('Invalid model output')
                for (key,baseline),value in zip(targets,values):
                    # Do not predict service before the earliest clinician finishes an active visit.
                    floor=min((max(1,minutes-max(0,(now-d['service_start_at']).total_seconds()/60)) if d['service_start_at'] else minutes if d['called_at'] else 0 for d in doctors),default=0)
                    results[key].update(minutes=round(max(0,float(value),floor),1),model_version=stored['version'],source='ai',reason='AI estimate from synthetic historical operations and current queue conditions. Not a guarantee.')
        except Exception as exc:
            LOG.warning('Live inference unavailable (%s); operational estimates used.',type(exc).__name__)
    return results


def current_prediction(conn,department_id,at=None,exclude=None,requirements=None):
    results=live_predictions(conn,department_id,at,prospective=None if exclude else (requirements or {}))
    return results.get(str(exclude) if exclude else 'prospective',dict(minutes=None,model_version=BASELINE,source='operational',reason='This token is no longer waiting.'))


def predict_for_token(conn,token):
    result=current_prediction(conn,token['department_id'],token['check_in_at'],token['id'])
    if result['minutes'] is not None and conn.execute('SELECT 1 FROM model_runs WHERE version=%s',(result['model_version'],)).fetchone():
        conn.execute('INSERT INTO predictions(token_id,predicted_wait_minutes,model_version,predicted_at) VALUES(%s,%s,%s,%s)',(token['id'],result['minutes'],result['model_version'],token['check_in_at']))
    conn.execute('UPDATE queue_tokens SET initial_wait_minutes=%s,initial_prediction_version=%s,initial_prediction_at=%s WHERE id=%s',(result['minutes'],result['model_version'],token['check_in_at'],token['id']))
    return result

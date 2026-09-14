"""Chronological evaluation of prior-only operational features on synthetic visits."""
import heapq
import json
from collections import deque
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction import DictVectorizer
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline

ROOT=Path(__file__).resolve().parents[2]


def features(tokens,schedules):
    output=[]
    for department,visits in tokens.groupby('department_id'):
        waiting=[];completed=[];recent=deque(maxlen=30);arrivals=deque()
        for row in visits.sort_values(['check_in_at','token_no']).to_dict('records'):
            now=row['check_in_at']
            while waiting and waiting[0]<=now:heapq.heappop(waiting)
            while completed and completed[0][0]<=now:
                _,duration=heapq.heappop(completed);recent.append(duration)
            while arrivals and (now-arrivals[0]).total_seconds()>1800:arrivals.popleft()
            active=int(((schedules.department_id==department)&(schedules.start_at<=now)&(schedules.end_at>now)).sum())
            local=now.tz_convert('Asia/Colombo')
            f=dict(department=str(department),queue_ahead=len(waiting),active_staff=active,recent_service=float(np.mean(recent)) if recent else 12.,arrivals_30m=len(arrivals),hour=local.hour,weekday=local.weekday())
            if pd.notna(row['service_start_at']):output.append(dict(features=f,target=(row['service_start_at']-now).total_seconds()/60,date=str(local.date())))
            departure=row['service_start_at'] if pd.notna(row['service_start_at']) else row['ended_at']
            if pd.notna(departure):heapq.heappush(waiting,departure)
            if pd.notna(row['completed_at']):heapq.heappush(completed,(row['completed_at'],(row['completed_at']-row['service_start_at']).total_seconds()/60))
            arrivals.append(now)
    return sorted(output,key=lambda r:r['date'])


def metrics(y,p):
    return dict(mae=round(float(mean_absolute_error(y,p)),4),rmse=round(float(np.sqrt(mean_squared_error(y,p))),4),r2=round(float(r2_score(y,p)),4))


def main():
    tokens=pd.read_csv(ROOT/'data/generated/queue_tokens.csv')
    for col in ['check_in_at','service_start_at','completed_at','ended_at']:tokens[col]=pd.to_datetime(tokens[col],utc=True,format="ISO8601")
    schedule=pd.read_csv(ROOT/'data/generated/staff_schedules.csv').merge(pd.read_csv(ROOT/'data/generated/staff.csv')[['id','department_id']],left_on='staff_id',right_on='id')
    for col in ['start_at','end_at']:schedule[col]=pd.to_datetime(schedule[col],utc=True,format="ISO8601")
    rows=features(tokens,schedule);days=sorted({r['date'] for r in rows});a,b=int(len(days)*.6),int(len(days)*.8)
    if a<2 or b>=len(days):raise ValueError('Generate several months of data before training.')
    train=[r for r in rows if r['date']<days[a]];val=[r for r in rows if days[a]<=r['date']<days[b]];test=[r for r in rows if r['date']>=days[b]]
    X=lambda split:[r['features'] for r in split]
    y=lambda split:np.array([r['target'] for r in split])
    baseline=lambda split:np.array([r['features']['queue_ahead']*r['features']['recent_service']/max(r['features']['active_staff'],1) for r in split])
    candidates={'Linear':Ridge(alpha=10),'Random Forest':RandomForestRegressor(n_estimators=100,max_depth=10,min_samples_leaf=8,random_state=42,n_jobs=2),'Gradient Boosting':GradientBoostingRegressor(n_estimators=120,max_depth=3,min_samples_leaf=10,random_state=42)}
    fitted={};validation={'Operational baseline':metrics(y(val),baseline(val))}
    for name,model in candidates.items():
        pipeline=make_pipeline(DictVectorizer(sparse=False),model);pipeline.fit(X(train),y(train));fitted[name]=pipeline;validation[name]=metrics(y(val),np.maximum(0,pipeline.predict(X(val))))
    best=min(validation,key=lambda k:validation[k]['mae'])
    selected=fitted.get(best)
    if selected:selected.fit(X(train+val),y(train+val))
    predicted=np.maximum(0,selected.predict(X(test))) if selected else baseline(test)
    version='synthetic-v1'
    report=dict(version=version,selected=best,dataset='Synthetic generator v1.0.0; seed 42',features=list(rows[0]['features']),train=dict(start=days[0],end=days[a-1],rows=len(train)),validation_period=dict(start=days[a],end=days[b-1],rows=len(val)),test=dict(start=days[b],end=days[-1],rows=len(test)),validation=validation,test_metrics=metrics(y(test),predicted),baseline_test=metrics(y(test),baseline(test)),by_department=[],by_hour=[],samples=[],limitations=['Synthetic data only; no real-world performance claim.','Features replay only events available before each arrival. Labels and final service duration never enter features.','Model choice uses validation MAE; selected model refits train+validation before one final test.','No probabilistic confidence intervals. Breaks, priority policies and atypical clinics can reduce accuracy.'])
    for field,dest in [('department','by_department'),('hour','by_hour')]:
        for value in sorted({r['features'][field] for r in test}):
            indexes=[i for i,r in enumerate(test) if r['features'][field]==value]
            if len(indexes)>1:report[dest].append(dict(group=value,count=len(indexes),**metrics(y(test)[indexes],predicted[indexes])))
    report['samples']=[dict(actual=round(test[i]['target'],2),predicted=round(float(predicted[i]),2),date=test[i]['date']) for i in range(0,len(test),max(1,len(test)//80))][:80]
    (ROOT/'ml/artifacts').mkdir(exist_ok=True);(ROOT/'ml/evaluation').mkdir(exist_ok=True)
    joblib.dump(dict(model=selected,version=version),ROOT/'ml/artifacts/wait_model.joblib')
    (ROOT/'ml/evaluation/results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['selected','test_metrics','baseline_test']},indent=2))


if __name__=='__main__':main()

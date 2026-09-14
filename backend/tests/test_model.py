import json
from pathlib import Path
import pandas as pd
from ml.src.train import features


def test_features_do_not_observe_future_completions():
    def stamp(t):return pd.Timestamp('2026-06-01T'+t+'+05:30')
    rows=pd.DataFrame([
        dict(department_id='d',token_no=1,check_in_at=stamp('08:00:00'),service_start_at=stamp('08:10:00'),completed_at=stamp('08:20:00'),ended_at=stamp('08:20:00')),
        dict(department_id='d',token_no=2,check_in_at=stamp('08:05:00'),service_start_at=stamp('08:30:00'),completed_at=stamp('08:40:00'),ended_at=stamp('08:40:00'))])
    schedules=pd.DataFrame([dict(department_id='d',start_at=stamp('07:00:00'),end_at=stamp('17:00:00'))])
    before=features(rows,schedules)
    rows.loc[0,'completed_at']=stamp('10:00:00');rows.loc[0,'ended_at']=stamp('10:00:00')
    after=features(rows,schedules)
    assert before[1]['features']==after[1]['features']
    assert before[1]['features']['queue_ahead']==1
    assert before[1]['features']['recent_service']==12
    assert not {'completed_at','ended_at','service_start_at','target'} & before[1]['features'].keys()


def test_evaluation_dates_are_disjoint_and_metrics_are_finite():
    data=json.loads(Path('ml/evaluation/results.json').read_text())
    assert data['train']['end']<data['validation_period']['start']
    assert data['validation_period']['end']<data['test']['start']
    assert data['test_metrics']['mae']>=0
    assert data['test_metrics']['rmse']>=data['test_metrics']['mae']
    assert data['selected'] in data['validation']

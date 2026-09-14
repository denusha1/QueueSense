"""Apply product migrations/grants and register the locally evaluated model."""
import json
import os
import subprocess
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import psycopg
from backend.local_run import configure
ROOT=Path(__file__).resolve().parents[1]


def main():
    url=configure(owner=True)
    subprocess.run([str(ROOT/'.venv/bin/python'),'database/scripts/manage.py','migrate'],cwd=ROOT,env={**os.environ,'DATABASE_URL':url},check=True)
    with psycopg.connect(url) as conn:
        conn.execute((ROOT/'database/sql/product_runtime_grants.sql').read_text())
        # The demo doctor's authority is tied to one clinician, not arbitrary request IDs.
        conn.execute("UPDATE staff SET user_id=(SELECT id FROM users WHERE email='doctor@demo.queuesense.test') WHERE id=(SELECT st.id FROM staff st JOIN departments d ON d.id=st.department_id WHERE d.code='GEN' ORDER BY st.display_name LIMIT 1) AND user_id IS NULL")
        report_path=ROOT/'ml/evaluation/results.json'
        if report_path.exists():
            report=json.loads(report_path.read_text());m=report['test_metrics'];zone=ZoneInfo('Asia/Colombo')
            begin=datetime.fromisoformat(report['train']['start']).replace(tzinfo=zone)
            end=datetime.fromisoformat(report['validation_period']['end']).replace(tzinfo=zone)+timedelta(days=1)
            conn.execute('INSERT INTO model_runs(model_name,version,training_start,training_end,mae,rmse,r2) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(version) DO NOTHING',(report['selected'],report['version'],begin,end,m['mae'],m['rmse'],m['r2']))
    print('Product schema, runtime grants, demo doctor assignment and model registry ready.')


if __name__=='__main__':main()

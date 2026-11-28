"""Run bounded Locust phases against a disposable loopback API and PostgreSQL schema."""

import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

import psutil
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.core.config import JwtSettings, Settings
from backend.core.security import HASHER
from backend.local_run import configure
from backend.services.auth import issue_session
from data.generator.generate import generate, write_dataset

MIX = ('patient', 'reception', 'patient', 'doctor', 'manager',
       'patient', 'reception', 'patient', 'doctor', 'auth')
NAME = 'queuesense_performance'
ORIGIN = 'http://127.0.0.1:3001'


def fixture(owner, schema, count):
    password_hash = HASHER.hash(secrets.token_urlsafe(32))
    jwt_key = secrets.token_urlsafe(32)
    os.environ['JWT_SIGNING_SECRET'] = jwt_key
    with psycopg.connect(owner, row_factory=dict_row) as conn:
        for path in sorted((ROOT / 'database/migrations').glob('*.sql')):
            conn.execute(path.read_text())
        with TemporaryDirectory(prefix='queuesense-perf-seed-') as temporary:
            seed = Path(temporary)
            write_dataset(generate(days=90), seed)
            conn.execute((seed / 'seed.sql').read_text())
        conn.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO queuesense_auth').format(sql.Identifier(schema)))
        for grants in ('auth', 'product'):
            conn.execute((ROOT / f'database/sql/{grants}_runtime_grants.sql').read_text())
        conn.execute('ANALYZE queue_sessions, queue_tokens, departments, staff, users, auth_sessions')
        department = conn.execute("SELECT id FROM departments WHERE code='GEN'").fetchone()['id']
        rows = conn.execute(
            "SELECT id FROM queue_tokens WHERE status='completed' ORDER BY check_in_at,id LIMIT %s",
            (count,),
        ).fetchall()
        if len(rows) != count:
            raise RuntimeError('Generate the synthetic dataset before running the benchmark.')
        keys = [secrets.token_urlsafe(32) for _ in rows]
        with conn.cursor() as cursor:
            cursor.executemany(
                '''
                INSERT INTO queue_tokens(session_id,department_id,staff_id,token_no,synthetic_patient_id,
                                         status,check_in_at,called_at,service_start_at,completed_at,ended_at,public_key)
                SELECT session_id,department_id,staff_id,%s,%s,status,check_in_at,called_at,
                       service_start_at,completed_at,ended_at,%s FROM queue_tokens WHERE id=%s
                ''',
                [(5000 + number, f'SYN-LOAD-CLOSED-{number}', key, row['id'])
                 for number, (key, row) in enumerate(zip(keys, rows, strict=True))],
            )
        # Give half of the patient VUs an active visit in another department.
        active = conn.execute("SELECT id FROM departments WHERE code <> 'GEN' ORDER BY code LIMIT 1").fetchone()['id']
        session = conn.execute("""
            INSERT INTO queue_sessions(department_id,service_date,opened_at)
            VALUES (%s,(now() AT TIME ZONE 'Asia/Colombo')::date,now())
            ON CONFLICT (department_id,service_date)
            DO UPDATE SET opened_at=queue_sessions.opened_at
            RETURNING id, closed_at
        """, (active,)).fetchone()
        if session['closed_at'] is None:
            for number in range(count):
                if number % len(MIX) not in (0, 5):
                    continue
                keys[number] = secrets.token_urlsafe(32)
                conn.execute("""
                    INSERT INTO queue_tokens(session_id,department_id,token_no,synthetic_patient_id,check_in_at,public_key)
                    VALUES (%s,%s,%s,%s,now(),%s)
                """, (session['id'], active, number + 1, f'SYN-LOAD-{number}', keys[number]))
        staff = {}
        settings = Settings(owner, (ORIGIN,), jwt=JwtSettings.from_env(required=True))
        for number in range(count):
            scenario = MIX[number % len(MIX)]
            if scenario == 'patient':
                continue
            role = 'admin' if scenario == 'auth' else scenario
            account = conn.execute(
                'INSERT INTO users(email,password_hash,role) VALUES(%s,%s,%s) RETURNING id,email,role',
                (f'load-{number}@staff.example.test', password_hash, role),
            ).fetchone()
            if role == 'doctor':
                conn.execute(
                    "INSERT INTO staff(department_id,display_name,user_id,staff_type) "
                    "VALUES(%s,%s,%s,'doctor')",
                    (department, f'Load doctor {number}', account['id']),
                )
            staff[str(number)] = issue_session(conn, settings, account, None, 'Load fixture')[0].access
        dates = conn.execute(
            "SELECT min(service_date) AS start,max(service_date) AS end FROM queue_sessions WHERE closed_at IS NOT NULL"
        ).fetchone()
    payload = dict(origin=ORIGIN, department=department, staff=staff,
                   patient_keys=keys, analytics_range=dates)
    return payload, jwt_key


def ready(base, api):
    deadline = monotonic() + 45
    while api.poll() is None and monotonic() < deadline:
        try:
            with urlopen(base + '/health', timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            sleep(0.25)
    raise RuntimeError('Load-test API did not become ready.')


def database_sample(conn):
    return conn.execute("""
        SELECT count(*) AS sessions,
               count(*) FILTER (WHERE state='active') AS active,
               count(*) FILTER (WHERE wait_event_type='Lock') AS waiting_locks
        FROM pg_stat_activity WHERE application_name=%s
    """, (NAME,)).fetchone()


def phase(args, count):
    directory = args.output / str(count)
    directory.mkdir(parents=True, exist_ok=True)
    schema = 'test_performance_' + uuid4().hex
    identifier = sql.Identifier(schema)
    owner = configure(owner=True)
    runtime = configure()
    scoped_owner = make_conninfo(owner, options=f'-c search_path={schema}')
    scoped_api = make_conninfo(runtime, application_name=NAME, options=f'-c search_path={schema}')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    with psycopg.connect(owner, autocommit=True, row_factory=dict_row) as monitor:
        monitor.execute(sql.SQL('CREATE SCHEMA {}').format(identifier))
        try:
            payload, jwt_key = fixture(scoped_owner, schema, count)
            with TemporaryDirectory(prefix='queuesense-perf-') as scratch, (directory / 'api.log').open('w') as log:
                path = Path(scratch) / 'fixture.json'
                path.touch(mode=0o600)
                path.write_text(json.dumps(payload, default=str))
                env = {key: val for key, val in os.environ.items() if not key.startswith('CHOREO_')}
                env.update(DATABASE_URL=scoped_api, JWT_SIGNING_SECRET=jwt_key,
                           JWT_ACCESS_TTL_SECONDS='600', JWT_REFRESH_TTL_SECONDS='28800',
                           FRONTEND_ORIGINS=ORIGIN, ENABLE_AUTOMATION='false',
                           ENABLE_DEMO_LOGIN='false', APP_ENV='development',
                           REQUEST_LOGS_ENABLED='false', METRICS_BEARER_TOKEN='',
                           DB_POOL_MAX_SIZE=str(args.pool), QUEUESENSE_LOAD_FIXTURE=str(path))
                api = subprocess.Popen(
                    [sys.executable, '-m', 'uvicorn', 'backend.app:create_app', '--factory',
                     '--host', '127.0.0.1', '--port', str(port), '--no-access-log', '--no-proxy-headers'],
                    cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                )
                try:
                    ready(base, api)
                    process = psutil.Process(api.pid)
                    process.cpu_percent()
                    with (directory / 'locust.log').open('w') as output:
                        client = subprocess.Popen(
                            [sys.executable, '-m', 'locust', '-f', str(ROOT / 'performance/locustfile.py'),
                             '--host', base, '--headless', '-u', str(count), '-r', str(count // 5),
                             '-t', f'{args.seconds}s', '--reset-stats', '--only-summary',
                             '--csv', str(directory.resolve() / 'requests'), '--exit-code-on-error', '2'],
                            cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT,
                        )
                        samples = []
                        started = monotonic()
                        try:
                            while client.poll() is None:
                                samples.append(dict(
                                    elapsed_s=round(monotonic() - started, 1),
                                    api_cpu_percent=process.cpu_percent(),
                                    api_rss_mib=round(process.memory_info().rss / 1024 ** 2, 2),
                                    **database_sample(monitor),
                                ))
                                sleep(1)
                        finally:
                            if client.poll() is None:
                                client.terminate()
                                client.wait(timeout=10)
                        (directory / 'resources.json').write_text(json.dumps(samples, indent=2) + '\n')
                        if client.returncode:
                            raise RuntimeError(f'Locust reported a failure. Inspect {directory}.')
                finally:
                    api.terminate()
                    try:
                        api.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        api.kill()
                        api.wait()
        finally:
            monitor.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(identifier))
    print(f'Completed {count} users. Results in {directory}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--users', type=int, nargs='+', choices=(10, 50, 100), default=(10, 50, 100))
    parser.add_argument('--seconds', type=int, default=45)
    parser.add_argument('--pool', type=int, default=0)
    args = parser.parse_args()
    if not 15 <= args.seconds <= 300 or not 0 <= args.pool <= 30:
        parser.error('Choose a bounded duration (15–300s) and pool size (0–30).')
    for count in args.users:
        phase(args, count)


if __name__ == '__main__':
    main()

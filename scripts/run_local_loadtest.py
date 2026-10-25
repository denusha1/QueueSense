"""Run the documented 100-user Locust scenario against the local synthetic demo."""
import os
import subprocess
import json
import socket
import time
import urllib.request
from pathlib import Path
import sys

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.local_run import configure

API_PORT = 8013
API_URL = f'http://127.0.0.1:{API_PORT}'


def main():
    with psycopg.connect(configure(owner=True)) as conn:
        row = conn.execute('SELECT public_key FROM queue_tokens ORDER BY check_in_at DESC LIMIT 1').fetchone()
    if not row:
        raise SystemExit('No synthetic token found. Seed the local demo first.')
    env = {**os.environ, 'QUEUESENSE_PATIENT_KEY': row[0]}
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', API_PORT)) == 0:
            raise SystemExit(f'Port {API_PORT} is already in use; load test did not start.')
    load_dir = ROOT / '.local/loadtest'
    load_dir.mkdir(parents=True, exist_ok=True)
    env.update({
        'DATABASE_URL': configure(),
        'ENABLE_DEMO_LOGIN': 'true',
        'ENABLE_AUTOMATION': 'false',
        'FRONTEND_ORIGINS': 'http://127.0.0.1:3002',
    })
    with (load_dir / 'api.log').open('a') as log:
        api = subprocess.Popen([
            str(ROOT / '.venv/bin/python'), '-m', 'uvicorn', 'backend.app:create_app', '--factory',
            '--host', '127.0.0.1', '--port', str(API_PORT), '--no-proxy-headers', '--no-access-log',
        ], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        for _ in range(90):
            if api.poll() is not None:
                raise SystemExit('Load-test API exited early; inspect .local/loadtest/api.log.')
            try:
                with urllib.request.urlopen(API_URL + '/health', timeout=2):
                    break
            except Exception:
                time.sleep(1)
        else:
            raise SystemExit('Load-test API did not become healthy; inspect .local/loadtest/api.log.')
        request = urllib.request.Request(f'{API_URL}/patient/{row[0]}', headers={'Referer': ''})
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
        if 'explanation' not in payload:
            raise SystemExit('The running API does not expose the SHAP response field.')
        command = [
            str(ROOT / '.venv/bin/locust'), '-f', str(ROOT / 'loadtests/locustfile.py'),
            '--host', API_URL, '--headless', '-u', '100', '-r', '10', '-t', '3m',
            '--csv', str(load_dir / 'local-100-users'), '--only-summary', '--exit-code-on-error', '2',
        ]
        subprocess.run(command, cwd=ROOT, env=env, check=True)
    finally:
        api.terminate()
        try:
            api.wait(timeout=10)
        except subprocess.TimeoutExpired:
            api.kill()
            api.wait()


if __name__ == '__main__':
    main()

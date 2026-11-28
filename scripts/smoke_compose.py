"""Build and exercise the full Compose stack in an isolated synthetic project."""

import argparse
import json
import os
import re
import secrets
import socket
import subprocess
from contextlib import ExitStack
from http.cookiejar import CookieJar
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def available_ports(count):
    with ExitStack() as stack:
        sockets = [stack.enter_context(socket.socket()) for _ in range(count)]
        for listener in sockets:
            listener.bind(('127.0.0.1', 0))
        return [listener.getsockname()[1] for listener in sockets]


def verify(compose, web_port, api_port, *, metrics_token):
    api = f'http://127.0.0.1:{api_port}'
    web = f'http://127.0.0.1:{web_port}'
    opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def fetch(base, path, body=None, *, extra_headers=None):
        headers = {} if body is None else {'Origin': web, 'Content-Type': 'application/json'}
        headers.update(extra_headers or {})
        request = Request(base + path, json.dumps(body).encode() if body is not None else None, headers)
        try:
            return opener.open(request, timeout=12)
        except HTTPError as response:
            return response

    def call(base, path, body=None):
        with fetch(base, path, body) as response:
            return response.status, response.read()

    status, health = call(api, '/health')
    assert (status, json.loads(health)) == (200, {'status': 'ok'})
    status, home = call(web, '/')
    assert status == 200 and b'QueueSense' in home
    stylesheet = re.search(rb'href="(/_next/static/[^"]+\.css)"', home)
    assert stylesheet and call(web, stylesheet[1].decode())[0] == 200
    assert call(web, '/api/service/queue/live')[0] == 401
    assert compose('exec', '-T', 'api', 'id', '-u', capture_output=True).stdout.strip() == '10001'
    assert compose('exec', '-T', 'frontend', 'id', '-u', capture_output=True).stdout.strip() != '0'
    print('PASS: PostgreSQL readiness, private API readiness, web rendering, and non-root app users.', flush=True)

    password = secrets.token_urlsafe(24)
    compose('exec', '-T', 'api', 'python', '-c', """
import sys
from backend.core.config import Settings
from backend.core.security import HASHER
from backend.database import connection

with connection(Settings.from_env()) as conn:
    conn.execute("INSERT INTO users(email, password_hash, role) VALUES (%s, %s, 'admin')",
                 ('smoke@example.test', HASHER.hash(sys.stdin.read())))
""", input=password)
    login, _ = call(web, '/api/auth/login', {'email': 'smoke@example.test', 'password': password, 'role': 'admin'})
    assert login == 200
    status, created = call(web, '/api/service/admin/departments', {
        'code': 'SMOKE', 'name': 'Synthetic smoke clinic', 'location': 'Test only', 'queue_threshold': 5,
    })
    assert status == 201
    status, issued = call(web, '/api/service/queue/check-in', {'department_id': json.loads(created)['id']})
    assert status == 201
    tracking_url = '/api/service/patient/' + json.loads(issued)['public_key']
    status, tracking = call(web, tracking_url)
    assert status == 200 and json.loads(tracking)['status'] == 'waiting'
    assert call(web, '/api/auth/logout', {})[0] == 200
    assert call(web, '/api/service/queue/live')[0] == 401
    print('PASS: web-to-API routing, JWT login/logout, database writes, and private patient tracking.', flush=True)

    compose('up', '--no-build', '--no-deps', '--force-recreate', '--wait', '--wait-timeout', '60', 'db')
    status, tracking = call(web, tracking_url)
    assert status == 200 and json.loads(tracking)['status'] == 'waiting'
    for service in ('api', 'frontend'):
        logs = compose('logs', '--no-color', '--tail', '20', service, capture_output=True)
        assert logs.stdout.strip(), f'{service} startup logs were empty'
    print('PASS: queue data survived PostgreSQL container replacement and application logs are accessible.', flush=True)


    if metrics_token:
        verify_faults(compose, api, web, tracking_url, fetch, metrics_token)


def verify_faults(compose, api, web, tracking_url, fetch, metrics_token):
    def expect(base, path, status, *, headers=None):
        with fetch(base, path, extra_headers=headers) as response:
            assert response.status == status, (status, response.status)
            return response.headers, response.read()

    expect(api, '/api/v1/queue', 401)
    expect(api, '/api/v1/queue', 401, headers={'Authorization': 'Bearer invalid.synthetic.jwt'})
    expect(web, '/api/service/internal/metrics', 404)
    expect(api, '/internal/metrics', 401)
    compose('stop', 'db')
    try:
        expect(api, '/health/live', 200)
        headers, body = expect(api, '/health', 503)
        payload = json.loads(body)
        assert payload['request_id'] == headers['X-Request-ID']
        assert payload['error']['code'] == 'service_unavailable'
        _, body = expect(web, tracking_url, 503)
        assert json.loads(body)['error']['code'] == 'service_unavailable'
    finally:
        compose('up', '--no-build', '--no-deps', '--wait', '--wait-timeout', '60', 'db')
    for _ in range(15):
        with fetch(api, '/health') as response:
            if response.status == 200:
                break
        sleep(1)
    else:
        raise AssertionError('API did not regain readiness after restarting PostgreSQL')
    expect(web, tracking_url, 200)
    print('PASS: database unavailable returned correlated 503; liveness stayed up and readiness recovered.', flush=True)

    for _ in range(82):
        with fetch(web, tracking_url) as response:
            if response.status == 429:
                assert int(response.headers['Retry-After']) > 0
                payload = json.load(response)
                request_id = response.headers['X-Request-ID']
                assert payload['request_id'] == request_id and payload['error']['code'] == 'rate_limited'
                break
            assert response.status == 200
    else:
        raise AssertionError('Expected private-link rate limiting during the local fixture test')
    _, metrics = expect(
        api, '/internal/metrics', 200, headers={'Authorization': 'Bearer ' + metrics_token},
    )
    assert b'route="/health",status="503"' in metrics
    assert b'route="/patient/{key}",status="429"' in metrics
    logs = compose('logs', '--no-color', 'api', capture_output=True).stdout
    assert request_id in logs
    assert request_id.replace('-', '') in logs
    tracking_key = tracking_url.rsplit('/', 1)[1]
    assert all(value not in logs and value.encode() not in metrics
               for value in (tracking_key, metrics_token, 'invalid.synthetic.jwt'))
    print('PASS: missing/invalid JWT and patient throttling; safe metrics and proxy-correlated logs.', flush=True)

    compose('stop', 'api')
    try:
        headers, body = expect(web, '/api/service/queue/live', 503)
        assert json.loads(body)['request_id'] == headers['X-Request-ID']
    finally:
        compose('up', '--no-build', '--wait', '--wait-timeout', '120', 'api')
    expect(api, '/health', 200)
    expect(web, '/api/service/queue/live', 401)
    print('PASS: Next.js returned correlated 503 while FastAPI was down and recovered after restart.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--faults', action='store_true', help='Exercise faults in the disposable stack.')
    args = parser.parse_args()
    try:
        docker = subprocess.run(
            ['docker', 'info', '--format', '{{.ServerVersion}}'],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        raise SystemExit('Install Docker and its Compose plugin before running the smoke.') from None
    if docker.returncode:
        raise SystemExit('Docker is unavailable. Start the Docker engine and check the active Docker context.')
    metrics_token = secrets.token_urlsafe(32) if args.faults else ''
    project = 'queuesense-smoke-' + uuid4().hex[:8]
    db_port, api_port, web_port = available_ports(3)
    with TemporaryDirectory(prefix='queuesense-compose-') as scratch:
        env = Path(scratch) / 'smoke.env'
        env.touch(mode=0o600)
        runtime_password = secrets.token_urlsafe(24)
        env.write_text(
            f'POSTGRES_PASSWORD={secrets.token_urlsafe(24)}\nPOSTGRES_PORT={db_port}\n'
            f'AUTH_DATABASE_URL=postgresql://queuesense_auth:{runtime_password}@db:5432/queuesense\n'
            f'JWT_SIGNING_SECRET={secrets.token_urlsafe(32)}\n'
            f'METRICS_BEARER_TOKEN={metrics_token}\nDB_POOL_MAX_SIZE={8 if args.faults else 0}\n'
            f'API_PORT={api_port}\nFRONTEND_PORT={web_port}\n'
            f'FRONTEND_ORIGINS=http://127.0.0.1:{web_port}\nENABLE_AUTOMATION=false\n'
            'APP_ENV=development\nLOCAL_BIND_ADDRESS=127.0.0.1\nHOST_BIND_ADDRESS=127.0.0.1\n'
        )
        base = ['docker', 'compose', '--env-file', str(env), '-p', project, '--profile', 'full']
        compose_keys = {
            line.split('=', 1)[0] for line in (ROOT / '.env.example').read_text().splitlines()
            if '=' in line and not line.startswith('#')
        }
        # Compose otherwise gives the caller's environment priority over the fixture file.
        isolated_env = {key: value for key, value in os.environ.items() if key not in compose_keys}

        def compose(*args, **kwargs):
            return subprocess.run([*base, *args], cwd=ROOT, env=isolated_env, check=True, text=True, **kwargs)

        try:
            for service in ('migrate', 'api', 'frontend'):
                compose('build', service)
            compose('up', '--no-build', '--wait', '--wait-timeout', '60', 'db')
            compose(
                'run', '--rm', '--no-deps', '-e',
                'COMPOSE_RUNTIME_URL=postgresql://queuesense_auth:REPLACE_ME@db:5432/queuesense', 'migrate',
            )
            print('PASS: database-only migration works with the example runtime credential.', flush=True)
            compose('up', '--no-build', '--wait', '--wait-timeout', '120', 'api', 'frontend')
            verify(compose, web_port, api_port, metrics_token=metrics_token)
            compose('ps')
        except BaseException:
            subprocess.run([*base, 'logs', '--no-color', '--tail', '80'], cwd=ROOT, env=isolated_env)
            raise
        finally:
            # This project and volume were just created for this synthetic run.
            compose('down', '--volumes')


if __name__ == '__main__':
    main()

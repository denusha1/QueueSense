"""Provision an isolated local PostgreSQL cluster and restricted authentication role.

Usage: .venv/bin/python -m backend.local_setup
Uses port 55432, never the default database port. No OS service is registered.
"""
import json
import os
import secrets
import subprocess
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'


def main():
    LOCAL.mkdir(mode=0o700, exist_ok=True)
    config_path = LOCAL / 'database.json'
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {'owner_password': secrets.token_urlsafe(32), 'runtime_password': secrets.token_urlsafe(32), 'port': 55432}
        fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as file:
            json.dump(config, file)
    portable_bin = LOCAL / 'pg-runtime/node_modules/@embedded-postgres/darwin-arm64/native/bin'
    pg_bin = Path(os.environ.get('POSTGRES_BIN', str(portable_bin if portable_bin.exists() else Path('/opt/homebrew/opt/postgresql@17/bin'))))
    cluster = LOCAL / 'postgres'
    password_file = LOCAL / 'init-password'
    if not (cluster / 'PG_VERSION').exists():
        password_file.write_text(config['owner_password'])
        password_file.chmod(0o600)
        try:
            subprocess.run([str(pg_bin / 'initdb'), '-D', str(cluster), '-U', 'queuesense_owner', '--auth=scram-sha-256', '--pwfile', str(password_file), '--encoding=UTF8', '--locale=C'], check=True)
        finally:
            password_file.unlink(missing_ok=True)
    running = subprocess.run([str(pg_bin / 'pg_ctl'), '-D', str(cluster), 'status'], capture_output=True).returncode == 0
    if not running:
        subprocess.run([str(pg_bin / 'pg_ctl'), '-D', str(cluster), '-l', str(LOCAL / 'postgres.log'), '-o', f"-h 127.0.0.1 -p {config['port']} -k {LOCAL}", '-w', 'start'], check=True)
    base = f"postgresql://queuesense_owner:{config['owner_password']}@127.0.0.1:{config['port']}"
    with psycopg.connect(base + '/postgres', autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname='queuesense'").fetchone():
            conn.execute('CREATE DATABASE queuesense OWNER queuesense_owner')
    owner_url = base + '/queuesense'
    subprocess.run([str(ROOT / '.venv/bin/python'), 'database/scripts/manage.py', 'migrate'], cwd=ROOT, env={**os.environ, 'DATABASE_URL': owner_url}, check=True)
    with psycopg.connect(owner_url) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='queuesense_auth'").fetchone():
            conn.execute(sql.SQL('CREATE ROLE queuesense_auth LOGIN PASSWORD {}').format(sql.Literal(config['runtime_password'])))
        conn.execute('GRANT CONNECT ON DATABASE queuesense TO queuesense_auth')
        conn.execute('GRANT USAGE ON SCHEMA public TO queuesense_auth')
        conn.execute('GRANT SELECT(id,email,password_hash,role,is_active) ON users TO queuesense_auth')
        conn.execute('GRANT UPDATE(password_hash) ON users TO queuesense_auth')
        conn.execute('GRANT SELECT,INSERT,DELETE ON auth_sessions,login_attempts TO queuesense_auth')
        conn.execute('GRANT USAGE,SELECT ON SEQUENCE login_attempts_id_seq TO queuesense_auth')
    subprocess.run([str(ROOT / '.venv/bin/python'), '-m', 'backend.seed_demo'], cwd=ROOT, env={**os.environ, 'DATABASE_URL': owner_url, 'ENABLE_DEMO_LOGIN': 'true'}, check=True)
    print('Local PostgreSQL ready on 127.0.0.1:55432. Runtime role has authentication-only permissions.')


if __name__ == '__main__':
    main()

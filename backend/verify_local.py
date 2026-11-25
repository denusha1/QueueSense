"""Run native PostgreSQL and authentication verification against the isolated local cluster."""
import os
import subprocess
from pathlib import Path
import psycopg
from backend.local_run import configure

ROOT = Path(__file__).resolve().parents[1]


def main():
    owner_url = configure(owner=True)
    runtime_url = configure()
    env = {**os.environ, 'DATABASE_URL': owner_url, 'TEST_DATABASE_URL': owner_url}
    python = str(ROOT / '.venv/bin/python')
    # Second run verifies migration tracking skips unchanged files cleanly.
    subprocess.run([python, 'database/scripts/manage.py', 'migrate'], cwd=ROOT, env=env, check=True)
    with psycopg.connect(owner_url) as conn:
        empty = not conn.execute('SELECT EXISTS(SELECT 1 FROM departments)').fetchone()[0]
    if empty:
        subprocess.run([python, 'database/scripts/manage.py', 'seed'], cwd=ROOT, env=env, check=True)
    with psycopg.connect(owner_url) as conn:
        for test in ('integrity.sql', 'identity_integrity.sql'):
            conn.execute((ROOT / 'database/tests' / test).read_text())
        conn.rollback()
    for statement in [
        'DELETE FROM users WHERE false',
        'DELETE FROM audit_logs WHERE false',
        'UPDATE audit_logs SET action=action WHERE false',
        'UPDATE patients SET created_at=created_at WHERE false',
        'DELETE FROM patients WHERE false',
        'DELETE FROM role_permissions WHERE false',
        'CREATE TABLE public.forbidden_probe(id integer)',
    ]:
        with psycopg.connect(runtime_url) as conn:
            try:
                conn.execute(statement)
            except psycopg.errors.InsufficientPrivilege:
                pass
            else:
                conn.rollback()
                raise AssertionError('Runtime role unexpectedly permitted: ' + statement)
    subprocess.run([python, '-m', 'pytest', 'backend/tests', '-q', '--tb=short'], cwd=ROOT, env=env, check=True)
    print('PASS: native migrations/re-run, full seed, integrity cases, restricted runtime permissions, authentication tests.')


if __name__ == '__main__':
    main()

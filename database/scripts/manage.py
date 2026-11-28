"""Transactional PostgreSQL migrations and explicit, non-destructive synthetic seeding."""
import argparse
import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def provision_compose_runtime(conn, url):
    """Apply application grants for the local Compose network only."""
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict

    runtime = conninfo_to_dict(url)
    if runtime.get('host') != 'db' or runtime.get('password') == 'REPLACE_ME':
        return
    if (
        runtime.get('user') != 'queuesense_auth'
        or runtime.get('dbname') != 'queuesense'
        or not runtime.get('password')
        or runtime.get('port', '5432') != '5432'
    ):
        raise RuntimeError('Set AUTH_DATABASE_URL for the restricted local queuesense_auth role')
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'queuesense_auth'").fetchone():
        conn.execute(
            sql.SQL('CREATE ROLE queuesense_auth LOGIN PASSWORD {}').format(
                sql.Literal(runtime['password'])
            )
        )
    for filename in ('auth_runtime_grants.sql', 'product_runtime_grants.sql'):
        conn.execute((ROOT / 'database/sql' / filename).read_text())
    print('Applied local API runtime grants.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['migrate', 'seed'])
    parser.add_argument('--file', type=Path, default=ROOT / 'data/generated/seed.sql')
    args = parser.parse_args()
    import psycopg
    url = os.environ.get('DATABASE_URL')
    local_password = os.environ.get('COMPOSE_POSTGRES_PASSWORD')
    if not url and local_password:
        from psycopg.conninfo import make_conninfo

        url = make_conninfo(host='db', dbname='queuesense', user='queuesense', password=local_password)
    if not url:
        parser.error('DATABASE_URL is required; see .env.example')
    with psycopg.connect(url) as conn:
        # Serialize schema/seed work. The context rolls back every change on failure.
        conn.execute('SELECT pg_advisory_xact_lock(72419021)')
        if args.command == 'migrate':
            conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())')
            for path in sorted((ROOT / 'database/migrations').glob('*.sql')):
                sql = path.read_text()
                checksum = hashlib.sha256(sql.encode()).hexdigest()
                row = conn.execute('SELECT checksum FROM schema_migrations WHERE version = %s', (path.name,)).fetchone()
                if row:
                    if row[0] != checksum:
                        raise RuntimeError('Applied migration changed: ' + path.name)
                    print('Already applied:', path.name)
                    continue
                conn.execute(sql)
                conn.execute('INSERT INTO schema_migrations(version,checksum) VALUES (%s,%s)', (path.name, checksum))
                print('Applied:', path.name)
            runtime_url = os.environ.get('COMPOSE_RUNTIME_URL')
            if local_password and runtime_url:
                provision_compose_runtime(conn, runtime_url)
        else:
            if conn.execute('SELECT EXISTS(SELECT 1 FROM departments)').fetchone()[0]:
                raise RuntimeError('Seed refused: database already contains departments. No data was changed. Use a separate empty demo database.')
            conn.execute(args.file.read_text())
            print('Seeded synthetic dataset:', args.file.name)
    print('Transaction committed.')


if __name__ == '__main__':
    main()

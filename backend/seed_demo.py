"""Explicit local demo accounts; never enable these in a production database."""
import os
import secrets
import psycopg
from backend.app import HASHER, WORKSPACES


def main():
    if os.environ.get('ENABLE_DEMO_LOGIN') != 'true' or os.environ.get('APP_ENV') == 'production':
        raise SystemExit('Demo seeding requires ENABLE_DEMO_LOGIN=true outside production.')
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        for role in WORKSPACES:
            # Random, undisclosed password. Explicitly enabled /auth/demo provides access.
            conn.execute('INSERT INTO users(email,password_hash,role) VALUES(%s,%s,%s) ON CONFLICT(email) DO NOTHING', (f'{role}@demo.queuesense.test', HASHER.hash(secrets.token_urlsafe(32)), role))
    print('Four local demo accounts ready; use Explore the demo on the login page.')


if __name__ == '__main__':
    main()

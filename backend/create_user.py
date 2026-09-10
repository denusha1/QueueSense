"""Provision a staff login locally; passwords are prompted, never CLI arguments."""
import argparse
import getpass
import os
import psycopg
from backend.app import Credentials, HASHER, WORKSPACES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--email', required=True)
    parser.add_argument('--role', choices=WORKSPACES, required=True)
    args = parser.parse_args()
    password = getpass.getpass('Password (12–128 characters): ')
    if not 12 <= len(password) <= 128:
        raise SystemExit('Password must be 12–128 characters.')
    if password != getpass.getpass('Confirm password: '):
        raise SystemExit('Passwords do not match.')
    body = Credentials(email=args.email, password=password, role=args.role)
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        conn.execute('INSERT INTO users(email,password_hash,role) VALUES(%s,%s,%s)', (body.email, HASHER.hash(body.password), body.role))
    print('Staff account created.')


if __name__ == '__main__':
    main()

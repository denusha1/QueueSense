"""Give each browser scenario a fresh window for the synthetic demo accounts."""

import os

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict


def main():
    url = os.environ['BROWSER_TEST_DATABASE_URL']
    settings = conninfo_to_dict(url)
    if settings.get('host') not in {'127.0.0.1', 'localhost', '::1'}:
        raise SystemExit('Browser fixture reset requires loopback PostgreSQL.')
    with psycopg.connect(url) as conn:
        database, schema = conn.execute('SELECT current_database(), current_schema()').fetchone()
        if database != 'queuesense_test' and not schema.startswith('test_'):
            raise SystemExit('Browser fixture reset requires queuesense_test or an isolated test_ schema.')
        conn.execute(
            sql.SQL("""
                DELETE FROM {}.api_traffic_budgets
                WHERE subject IN (
                    SELECT id FROM {}.users WHERE email = ANY(%s)
                )
            """).format(sql.Identifier(schema), sql.Identifier(schema)),
            ([f'{role}@demo.queuesense.test' for role in ('admin', 'reception', 'doctor', 'manager')],),
        )


if __name__ == '__main__':
    main()

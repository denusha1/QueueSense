# Database foundation

## Start with Docker Compose

Install Docker with Compose first. From the repository root:

```sh
cp .env.example .env
# Edit .env and set a nonempty POSTGRES_PASSWORD (URL-safe letters/digits).
python3 data/generator/generate.py
docker compose up -d db
docker compose run --rm migrate
docker compose --profile demo run --rm seed
```

The database listens only on `127.0.0.1:5432` by default. Named storage persists across restarts. Set `POSTGRES_PORT` for another host port. `.env` and full generated data are ignored by git and excluded from build context. Do not delete volumes to solve a seed error; seeding intentionally refuses databases that already contain departments. Use a separate Compose project and host port for a fresh dataset.

To inspect counts:

```sh
docker compose exec db psql -U queuesense -d queuesense -c 'SELECT count(*) FROM queue_tokens;'
docker compose exec db psql -U queuesense -d queuesense -c 'SELECT version FROM schema_migrations ORDER BY version;'
```

## Existing PostgreSQL without Docker

```sh
python3 -m venv .venv
.venv/bin/pip install -r database/requirements.txt
# Set DATABASE_URL in your shell to your local PostgreSQL connection.
.venv/bin/python database/scripts/manage.py migrate
python3 data/generator/generate.py
.venv/bin/python database/scripts/manage.py seed
```

The CLI reads environment variables; it does not auto-load `.env`. Do not paste real credentials into logs or source code. Schema migration tracking uses checksums and a transaction lock. A failed migration/seed rolls back and the CLI exits nonzero.

## Reproducible SQL verification without Docker

```sh
python3 data/generator/generate.py
python3 -m unittest discover -s data/generator -p 'test_*.py' -v
npm ci --prefix database
npm test --prefix database
```

The database test dependency runs **embedded PostgreSQL via PGlite**; it is test tooling only, not the application database. Tests apply every migration, insert the full generated dataset, reconcile counts and SQL/Python waits, validate a full queue lifecycle, reject 11 invalid writes and verify rollback. This does not verify Docker, host networking, the native psycopg CLI, least-privilege runtime roles, or production Postgres deployment.

Validated in this workspace: Python 3.9.6, Node 25.6.1, PGlite 0.5.8. Docker and native PostgreSQL were unavailable, so the Compose/native path is supplied but not executed. The Docker helper uses Python 3.12 and PostgreSQL 17; smoke-test that path after installing Docker.

See [data dictionary](../data/data_dictionary.md) and [ER diagram](../docs/architecture/database.md).

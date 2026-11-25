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

For migrations 013 and 014, confirm PostgreSQL provides `btree_gist`, run the
preflight checks, and reapply the product runtime grants after migrating. See
[database design and upgrade workflow](../docs/DATABASE_DESIGN.md).

## Reproducible SQL verification without Docker

```sh
python3 data/generator/generate.py
python3 -m unittest discover -s data/generator -p 'test_*.py' -v
npm ci --prefix database
npm test --prefix database
```

The database test dependency runs embedded PostgreSQL via PGlite. The test
loads legacy rows before migration 013, verifies they survive the upgrade,
checks seed counts and wait KPIs, and rolls back integrity probes. Run
`.venv/bin/python -m backend.verify_local` to exercise the native PostgreSQL
migration CLI, permissions, and concurrent application traffic.

[Data dictionary](../data/data_dictionary.md) · [Current ER diagram](../docs/DATABASE_DESIGN.md#entity-relationships)

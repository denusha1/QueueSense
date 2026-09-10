# QueueSense

Patient flow and waiting-time analytics for healthcare operations. QueueSense brings queue events, operational insights and, in later stages, evaluated waiting-time predictions together. The planned stack is Next.js / TypeScript, FastAPI, PostgreSQL, Pandas and scikit-learn.

## Current progress

- **Step 1 approved:** responsive welcome/login interface, four workspace roles, credential field validation, password visibility and role previews.
- **Step 2 approved:** PostgreSQL schema and migrations, synthetic data generator, integrity tests, Docker setup, and a browsable dataset snapshot.
- **Step 3 ready for review:** real FastAPI/PostgreSQL authentication, server-side role permissions, sessions and logout.
- **Next:** live queue operations, after user review.

Login now connects to FastAPI and PostgreSQL. Passwords are hashed with Argon2id; session tokens are stored as hashes. Choose a role and use **Explore the demo → Enter … demo** for a real local demo session. Operational controls and trained models are still planned; all clinic records remain fictional.

## Open the running preview

[Demo Data review](http://127.0.0.1:3001/demo-data) · [Welcome page](http://127.0.0.1:3001)

These links are local to the Mac running the server, not public deployments. The data page reads a saved generated snapshot; it does not report live PostgreSQL data or connection health.

## Run frontend

```sh
cd frontend
npm ci
npm run dev -- --port 3001
```

Build and production preview:

```sh
npm run build
npm run start -- --port 3001
```

## Database and dataset

The default generator produces 90 calendar days, 15,265 fictional tokens, three departments, nine demo clinicians and 234 sessions. Full CSVs and seed SQL are generated locally; the small snapshot is committed. Database deliverables include 12 domain tables, three migrations, partial indexes, queue/timestamp/event validation, SQL metric views, and transactional migration/seed commands.

See [database setup](database/README.md), [data dictionary](data/data_dictionary.md), [ER diagram](docs/architecture/database.md), and [full implementation plan](docs/IMPLEMENTATION_PLAN.md).

```sh
python3 data/generator/generate.py
python3 -m unittest discover -s data/generator -p 'test_*.py' -v
npm ci --prefix database
npm test --prefix database
```

Rebuild the frontend after changing the generated snapshot.

## Validation and limits

Seven generator tests pass. Embedded PostgreSQL checks apply all migrations, load the complete dataset, reconcile SQL/Python metrics, validate the queue lifecycle, reject 11 invalid writes, and check rollback. The frontend production build includes TypeScript validation.

Native PostgreSQL 17.10 now runs locally on port 55432, with all four migrations and the synthetic seed applied. Native integrity checks, restricted-role checks and 12 authentication API tests pass. Docker Compose remains unexecuted. PGlite remains optional SQL test tooling. See [authentication setup and behavior](backend/README.md).

Start the auth service before the frontend:

```sh
.venv/bin/python -m backend.local_setup
.venv/bin/python -m backend.local_run
```

Full local database/API verification: `.venv/bin/python -m backend.verify_local`. API docs: http://127.0.0.1:8001/docs.

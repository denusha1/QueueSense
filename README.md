# QueueSense

Patient flow and waiting-time analytics for healthcare operations. QueueSense brings queue events, operational insights and, in later stages, evaluated waiting-time predictions together. The planned stack is Next.js / TypeScript, FastAPI, PostgreSQL, Pandas and scikit-learn.

## Current progress

- **Step 1 approved:** responsive welcome/login interface, four workspace roles, credential field validation, password visibility and role previews.
- **Step 2 ready for review:** PostgreSQL schema and migrations, synthetic data generator, integrity tests, Docker setup, and a browsable dataset snapshot.
- **Next:** actual authentication and role enforcement, after user review.

The login is a UI preview. Authentication, operational APIs and prediction models are not connected. Entered credentials are not transmitted or persisted. All visible clinic records are fictional.

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

Docker and native PostgreSQL are not installed in this workspace, so the supplied Docker Compose and psycopg CLI paths have not been executed. PGlite is used only for SQL testing; it does not substitute for the planned deployed PostgreSQL service. Real authentication and runtime database permissions are the next stage.

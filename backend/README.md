# Backend: authentication and product services

Next.js proxies fixed authentication routes to FastAPI. FastAPI checks passwords and sessions against PostgreSQL. The browser's selected role is never an authorization source: every workspace checks the persisted user role, including direct backend requests. Role workspaces now provide operational, analytics and administrative tools; see `docs/DELIVERY.md` for the complete feature matrix.

## Backend layout

The Uvicorn entry point is `backend.app:create_app --factory`. The factory wires the shared middleware, error handlers, lifespan and feature routers. Existing URLs and the same-origin Next.js proxy contract are preserved.

| Path | Responsibility |
| --- | --- |
| [`api/router.py`](api/router.py), [`api/endpoints/`](api/endpoints) | Compose the HTTP surface. Endpoints validate requests, declare dependencies and translate results to cookies, JSON, downloads or SSE. SQL and transaction control live below this layer. |
| [`api/dependencies.py`](api/dependencies.py) | `AppSettings` and `CurrentUser` inject configuration and the authenticated staff session. Tests can override them through FastAPI. |
| [`core/`](core) and [`schemas/`](schemas) | Typed application and provider settings, credential primitives, shared authorization, error types and common Pydantic request models. Some request models remain with their feature modules to retain existing OpenAPI schema names. |
| [`services/`](services), [arrivals](arrivals.py), [planning](planning.py), [accounts](accounts.py) | Application use cases own authorization, domain rules and transaction lifetime. Queue and QR arrivals share token issuance. Both staff queue list endpoints use the same wait and position projection. Existing feature modules also implement notifications, delivery, feedback and paging. |
| [`repositories/`](repositories), [`database.py`](database.py) | Shared SQL for sessions, audit, queue actions, schedules and readiness. Repositories use the caller's connection so token, visit event, audit and appointment linkage writes can commit together. Feature-specific read/report queries remain with their services. |

Blocking PostgreSQL queries, password hashing, model inference and reports stay in synchronous handlers so FastAPI can run them in worker threads. The PostgreSQL listener uses an async connection for SSE, and the async lifespan sends blocking automation and delivery work to a thread. The refactor keeps existing locking, transaction boundaries, and prediction fallback behavior.

Configuration comes from [the root environment template](../.env.example) and is loaded by [`core/config.py`](core/config.py). The app factory also accepts an explicit `Settings` instance. Provider configuration is read when needed. Add feature routes to their feature adapter and put new shared queries in a repository.

[Central error handlers](api/errors.py) use the same safe JSON envelope for versioned and legacy routes. The legacy `detail` field remains available to browser callers. Logs contain the request ID, registered route template, HTTP method, and exception class. Raw request paths, session cookies, submitted validation values and SQL diagnostics are excluded from those events. See the [API error reference](../docs/API_REFERENCE.md#error-contract).

## Timeouts and transactions

| Runtime setting | Default | Scope |
| --- | --- | --- |
| `DB_CONNECT_TIMEOUT_SECONDS` | 5 s | PostgreSQL client connection attempt |
| `DB_STATEMENT_TIMEOUT_MS` | 20,000 ms | Individual application SQL statements |
| `DB_LOCK_TIMEOUT_MS` | 5,000 ms | PostgreSQL lock acquisition |

The settings are positive integers validated at startup. The regular psycopg
connection context commits only on success. A statement or lock timeout rolls
back the request transaction and returns 504. Database connection failures
return 503. Import row errors roll back to a savepoint, while database timeouts
or infrastructure errors abort the whole import. QR issuance and queue
transitions retain their existing transaction boundaries.

The Next.js auth proxy waits up to 10 seconds and the service proxy up to 60
seconds for the upstream response. A proxy timeout does not determine whether a
mutation committed before the response was lost. Reconcile current state before
resubmitting a write. SSE handles database failures by logging the request ID and
closing the stream so the browser can reconnect. Configure hosting ingress
limits separately for slow uploads and direct traffic.

## Local setup

Use Python 3.12 and PostgreSQL 17 binaries. Install dependencies into the project virtual environment:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
.venv/bin/python -m backend.local_setup
.venv/bin/python -m backend.local_run
```

`local_setup` auto-detects the project-local portable binaries first, then `/opt/homebrew/opt/postgresql@17/bin`; set `POSTGRES_BIN` for other installations. This session uses native PostgreSQL 17.10 from the [portable binary package](https://github.com/leinelissen/embedded-postgres) because Homebrew downloads failed. The cluster is real PostgreSQL, not the PGlite test runtime. On Apple Silicon, install the same local binaries with `npm install --prefix .local/pg-runtime @embedded-postgres/darwin-arm64@17.10.0-beta.17`. It creates a project-local cluster in ignored `.local/postgres`, on `127.0.0.1:55432`, with SCRAM password authentication. Credentials are randomly generated and written to `.local/database.json` with mode 0600. It applies migrations idempotently, creates a restricted `queuesense_auth` runtime role and provisions four explicit local demo accounts. It does not register an OS startup service.

Start frontend separately:

```sh
cd frontend
npm run build
npm run start -- --port 3001
```

Open http://127.0.0.1:3001, choose a role, click **Explore the demo**, then **Enter … demo**. Demo accounts have undisclosed random password hashes. The explicit demo endpoint issues a real session only when `ENABLE_DEMO_LOGIN=true`; it is disabled by default in the general API factory and prohibited by production environment configuration. Local runner enables it intentionally.

To provision a private staff login in an existing migrated database, set owner `DATABASE_URL` in your shell and run:

```sh
.venv/bin/python -m backend.create_user --email staff@example.test --role reception
```

The command prompts for a 12–128 character password and confirmation without echoing it. The command leaves existing accounts intact. Role options are reception, doctor, manager and admin. Account administration, recovery and administrator MFA are documented with provider setup. [Accounts and delivery](../docs/ACCOUNTS_AND_NOTIFICATIONS.md)

## Security behavior

- Argon2id password hashes, with verification against a dummy hash for nonexistent accounts and rehash-on-login when parameters change.
- Staff access uses short-lived JWTs when configured. A rotating opaque refresh cookie lasts up to the absolute session deadline. PostgreSQL stores only its digest. Production requires JWT configuration. [Staff JWT settings and trust boundaries](../docs/JWT_AUTHENTICATION.md)
- Successful login replaces the caller's previous session. Logout deletes the session server-side. Expired or disabled-account sessions fail immediately. User role changes affect subsequent requests without trusting stale browser claims.
- State-changing requests require an exact allowlisted Origin. Next.js additionally enforces its own same-origin check and forwards allowlisted authentication and account paths. Credentials are never placed in localStorage. Proxy requests are limited to 4 KiB and have timeouts.
- Failed account attempts are limited to five in 15 minutes; all attempts from the backend peer are limited to 60. Counts live in PostgreSQL and are serialized with a transaction lock. Behind the Next.js proxy the peer limit is intentionally shared, not a claim of individual-client IP detection; deployment should configure an appropriate trusted edge rate limiter for higher traffic.
- API runtime role has explicit authentication and product-table grants, including the writes required for administrator features. It cannot create schema objects, delete user accounts or act as database owner. End-user role permissions are enforced in FastAPI before each protected operation. See `database/sql/auth_runtime_grants.sql` and `database/sql/product_runtime_grants.sql`.
- Authentication responses use no-store. API database errors return a generic 503. Structured logs record the error class and route template.
- Staff account management includes an administrator-only user-management UI, recovery and optional administrator TOTP enrollment. The public deployment and HTTPS setup have separate verification requirements.

## API

| Method | Path | Behavior |
| --- | --- | --- |
| POST | /auth/login | Email, password, selected role → verified user and session cookie |
| GET | /auth/me | Current persisted user role and session expiry; 401 without valid session |
| POST | /auth/logout | Revoke current session and expire cookie |
| GET | /auth/demo | Whether explicitly enabled demo entry is available |
| POST | /auth/demo | Local-only configured demo account for the requested role |
| GET | /auth/workspace/{role} | Role-gated workspace information; 403 for mismatched roles |
| GET | /health | Database/table connectivity probe |

Local API docs: http://127.0.0.1:8001/docs. Browser client uses `/api/auth/*` on the frontend so backend cookies stay same-origin. Backend must remain private behind the frontend in deployment.

### Versioned staff API

The private `/api/v1` API covers staff login, cookie refresh and logout, patient
registry access, queue records and history, the doctor directory and schedules,
and aggregate analytics. Apply migrations through 016 and reapply the auth and product
runtime grants before use. [Endpoint reference](../docs/API_REFERENCE.md)

### Patient identity

`POST /patients` registers or resolves a clinic identifier for authorized reception
staff. Its response contains the registry UUID. Staff can use that UUID as an
optional `patient_id` in queue check-in and appointment booking. Legacy browser
requests still work without it. Apply migrations 013 and 014 and the updated
product runtime grants before starting this version.
[Database design and migration workflow](../docs/DATABASE_DESIGN.md)

## Tests

```sh
.venv/bin/python -m backend.verify_local
```

This re-runs native migrations, loads synthetic data if the local database is empty, runs SQL integrity checks inside a rolled-back transaction, verifies restricted runtime permissions, and runs the API tests. API tests use a uniquely named temporary schema and remove only that schema afterward; application accounts/data are not truncated.

For a separately managed PostgreSQL database:

```sh
TEST_DATABASE_URL='your-local-test-connection' .venv/bin/python -m pytest backend/tests -q
```

Tests cover authentication, authorization, lifecycle, scheduling, arrivals, reports and inference. The architecture regression tests cover dependency overrides, safe structured database error logging, consistent public-key-free staff queue views, and concurrent scheduling. Compare sorted OpenAPI JSON before and after route refactors to catch frontend contract drift.

## Docker / deployment configuration

The optional Compose `auth` profile provides the API container. Provision a restricted `queuesense_auth` PostgreSQL role and apply the grants file first, then set `AUTH_DATABASE_URL` in root `.env` to that role's URL and run `docker compose --profile auth up -d api`. Do not give the API the database-owner URL. Docker execution is not verified on this Mac.

Production requires `APP_ENV=production`, HTTPS-only `FRONTEND_ORIGINS`, disabled demo login, an HTTPS frontend and a provisioned `JWT_SIGNING_SECRET`. Set frontend server-only `AUTH_API_URL` to the private API address. Apply the supplied product runtime grants for the implemented queue, analytics and administrative services.

See [verification history](../docs/TEST_RESULTS.md) for past results. The API remains private behind Next.js in this stage. The [enterprise API design](../docs/API_ARCHITECTURE.md) describes the proposed versioned integration surface and Choreo gateway.

Product API endpoints and interactive schemas are exposed in the running FastAPI `/docs`. Model source/evaluation, CSV contracts, metrics and full delivery limits are documented in `ml/README.md`, `data/data_dictionary.md` and `docs/DELIVERY.md`.

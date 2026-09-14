# Backend: authentication and product services

Next.js proxies fixed authentication routes to FastAPI. FastAPI checks passwords and sessions against PostgreSQL. The browser's selected role is never an authorization source: every workspace checks the persisted user role, including direct backend requests. Role workspaces now provide operational, analytics and administrative tools; see `docs/DELIVERY.md` for the complete feature matrix.

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

The command prompts for a 12–128 character password and confirmation without echoing it. Duplicate accounts are not overwritten. Role options: reception, doctor, manager, admin. Password recovery currently directs users to their administrator; reset emails and account administration UI are not implemented.

## Security behavior

- Argon2id password hashes, with verification against a dummy hash for nonexistent accounts and rehash-on-login when parameters change.
- 256-bit random opaque session cookies; only SHA-256 token hashes are stored server-side. Cookie is HttpOnly, SameSite=Lax, path `/`, lifetime eight hours; Secure when `APP_ENV=production`.
- Successful login replaces the caller's previous session. Logout deletes the session server-side. Expired or disabled-account sessions fail immediately. User role changes affect subsequent requests without trusting stale browser claims.
- State-changing requests require an exact allowlisted Origin. Next.js additionally enforces its own same-origin check and only forwards fixed login/logout/me/demo paths. Credentials are never placed in localStorage. Proxy requests are limited to 4 KiB and have timeouts.
- Failed account attempts are limited to five in 15 minutes; all attempts from the backend peer are limited to 60. Counts live in PostgreSQL and are serialized with a transaction lock. Behind the Next.js proxy the peer limit is intentionally shared, not a claim of individual-client IP detection; deployment should configure an appropriate trusted edge rate limiter for higher traffic.
- API runtime role has explicit authentication and product-table grants, including the writes required for administrator features. It cannot create schema objects, delete user accounts or act as database owner. End-user role permissions are enforced in FastAPI before each protected operation. See `database/sql/auth_runtime_grants.sql` and `database/sql/product_runtime_grants.sql`.
- Authentication responses use no-store. API database errors return a generic 503; logs contain error class/path, not credentials, cookies or connection URLs.
- An administrator-only user-management UI is implemented. Public registration, self-service password reset and MFA are not implemented. Public deployment and HTTPS are not configured yet.

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

## Tests

```sh
.venv/bin/python -m backend.verify_local
```

This re-runs native migrations, loads synthetic data if the local database is empty, runs SQL integrity checks inside a rolled-back transaction, verifies restricted runtime permissions, and runs the API tests. API tests use a uniquely named temporary schema and remove only that schema afterward; application accounts/data are not truncated.

For a separately managed PostgreSQL database:

```sh
TEST_DATABASE_URL='your-local-test-connection' .venv/bin/python -m pytest backend/tests -q
```

Tests cover password login for all four roles, direct API cross-role denial, cookies, hashed session storage, rotation/logout, bad credentials, expiry, account disabling, CSRF, throttling across app restarts, demo flag, input validation and production cookie attributes.

## Docker / deployment configuration

The optional Compose `auth` profile provides the API container. Provision a restricted `queuesense_auth` PostgreSQL role and apply the grants file first, then set `AUTH_DATABASE_URL` in root `.env` to that role's URL and run `docker compose --profile auth up -d api`. Do not give the API the database-owner URL. Docker execution is not verified on this Mac.

Production requires `APP_ENV=production`, HTTPS-only `FRONTEND_ORIGINS`, disabled demo login and an HTTPS frontend. Set frontend server-only `AUTH_API_URL` to the private API address. Apply the supplied product runtime grants for the implemented queue, analytics and administrative services.

Verified for this delivery: 12 native PostgreSQL API tests passed; browser checks passed for all four demo sign-ins, refresh persistence, HttpOnly cookies, denied cross-role pages, logout revocation, incorrect credentials, origin rejection and mobile layout. Next.js production build and TypeScript validation passed. Two dependency deprecation warnings appeared in the Python test client; they did not fail tests.

Product API endpoints and interactive schemas are exposed in the running FastAPI `/docs`. Model source/evaluation, CSV contracts, metrics and full delivery limits are documented in `ml/README.md`, `data/data_dictionary.md` and `docs/DELIVERY.md`.

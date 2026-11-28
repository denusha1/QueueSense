# QueueSense Docker setup

## Start the development stack

1. From the QueueSense repository root, copy `.env.example` to `.env`. Set a strong local `POSTGRES_PASSWORD`. In `AUTH_DATABASE_URL`, replace `REPLACE_ME` with a different password encoded for a URI. Leave the local runtime user as `queuesense_auth` and the database host as `db`. The migration job creates the role on first use and applies the application's database grants. It preserves the password on an existing role. Rotate that role deliberately if its password changes.
2. Optionally set `JWT_SIGNING_SECRET` to a privately generated base64url value with at least 32 random bytes to exercise JWT. Run the stack.

```sh
docker compose --profile full up -d --build --wait api frontend
docker compose --profile full ps
```

3. Open `http://127.0.0.1:3001`. The API readiness check is available on `http://127.0.0.1:8001/health`. The schema starts empty. Create an approved local staff account before using the staff workspace. The command prompts for the password.

```sh
docker compose --profile full exec api python -m backend.create_user --email admin@example.test --role admin
```

The demo seed is an explicit operation for a separate empty database. [Backend account and synthetic demo instructions](../backend/README.md)

## Networking, data and health

| Service | Container address | Startup and data |
| --- | --- | --- |
| PostgreSQL | `db:5432` on the data network | `pg_isready` health check. Data persists in the `postgres_data` named volume. |
| Migration | One-shot job on the data network | Waits for PostgreSQL, applies migrations transactionally, then grants local runtime privileges. FastAPI waits for successful completion. |
| FastAPI | `api:8001` on the service network | `GET /health` checks access to the PostgreSQL schema using the restricted runtime account. |
| Next.js | `frontend:3000` on the service network | HTTP home page health check. Startup waits for FastAPI readiness and the server uses `http://api:8001` for backend requests. |

Next.js has no connection to the data network. The three published host ports default to loopback. Edit only the intended host bindings, port values, and exact `FRONTEND_ORIGINS` when testing a LAN deployment. Behind Compose, use service DNS and container ports. The frontend runtime contains the traced standalone output, public files and static assets. Its build uses `npm ci`. The backend image copies a Python environment installed from its lockfile. The API, web and migration containers use non-root accounts with no added Linux capabilities. Enable a secret manager and a managed PostgreSQL connection for a hosted deployment. [Deployment architecture](DEPLOYMENT_ARCHITECTURE.md)

```sh
docker compose --profile full logs --tail=100 api frontend
docker compose logs --tail=100 db migrate
docker compose --profile full down
```

Normal shutdown keeps the database volume. The isolated smoke command below creates and removes only its own disposable project and volume. It uses temporary secrets and a synthetic staff account and visit. The smoke checks the frontend’s static assets, staff sign-in and queue tracking, then verifies that the visit survives PostgreSQL container replacement.

```sh
python3 scripts/smoke_compose.py
```

For production, provision the database and apply migrations separately using an approved release identity. Keep FastAPI and PostgreSQL private, use HTTPS at ingress, set `APP_ENV=production`, disable demo sign-in, and inject a signing secret and the other required environment configuration at runtime. QueueSense's Choreo integration uses a dedicated HTTPS origin. [Deployment configuration](DEPLOYMENT.md) · [Choreo origin](../api-management/proxy-configuration.md)

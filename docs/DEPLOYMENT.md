# Deployment configuration

Local native PostgreSQL + API + frontend has been run and tested. Docker is not installed in the current workspace, so the Docker path below is provided but has not been executed. No public cloud deployment is claimed.

## Docker services

1. Copy `.env.example` to `.env`. Set a private URL-safe `POSTGRES_PASSWORD`.
2. Generate synthetic files: `python3 data/generator/generate.py`.
3. Run `docker compose up -d db`, then `docker compose run --rm migrate` and `docker compose --profile demo run --rm seed` against a new demo database.
4. As the database owner, create a `queuesense_auth` LOGIN role with a private password. Apply `database/sql/auth_runtime_grants.sql` and `database/sql/product_runtime_grants.sql` to that database.
5. Set root `.env` `AUTH_DATABASE_URL=postgresql://queuesense_auth:YOUR_PASSWORD@db:5432/queuesense`. This account must not own the schema or be a superuser.
6. Provision staff accounts using `backend.create_user` with an owner connection. Demo seeding is explicit and for non-production only.
7. Run `docker compose --profile full up --build -d api frontend`. The frontend listens at http://127.0.0.1:3001; the API is private to the compose network with a local-only diagnostics port.

The API image includes the repository-owned model artifact. Register the model version and metrics in `model_runs` before persisting predictions; `backend/bootstrap_product.py` performs that step for the native local cluster. For a separate deployment, use the values in `ml/evaluation/results.json` and preserve matching model versions. The service still returns estimates when an artifact exists but will not write a prediction against a missing registry version.

## Public deployment

Use an HTTPS reverse proxy or host-provided TLS in front of Next.js. Keep PostgreSQL and FastAPI on a private network. Set `APP_ENV=production`, disable `ENABLE_DEMO_LOGIN`, and set the identical explicit HTTPS `FRONTEND_ORIGINS` in API and frontend. Set frontend `AUTH_API_URL` to the private backend address. Preserve the original Host and Origin at the proxy; untrusted cross-origin writes are rejected.

Provision credentials outside source control. Configure PostgreSQL backups, TLS where needed, resource limits, a trusted edge rate limiter and operational monitoring. The runtime currently has product-level table grants and enforces end-user roles in FastAPI; do not expose database credentials directly to browsers. Public demo deployments need separate synthetic-only data/accounts and an explicit access policy; the production configuration deliberately rejects open demo-login mode.

The repository has an origin remote, but no public push, hosting account changes, paid resources or DNS modifications were performed during this delivery.

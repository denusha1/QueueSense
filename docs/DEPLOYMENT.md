# Deployment configuration

See [Docker setup](DOCKER_SETUP.md) for the current Compose startup and verification workflow.

The native PostgreSQL stack and the full Docker Compose stack have been tested locally.

## Docker services

Use [Docker setup](DOCKER_SETUP.md) to configure credentials, start the services and create a staff account. The migration job applies local runtime grants when `AUTH_DATABASE_URL` contains a configured local password. A database-only run can leave the example placeholder in place.

For an explicitly synthetic demo, generate fixtures with `python3 data/generator/generate.py` and run `docker compose --profile demo run --rm seed` against an empty demo database. Set `FRONTEND_ORIGINS` to the exact browser origin. For a LAN test, set `HOST_BIND_ADDRESS` to the intended interface and include the exact LAN origin, such as `http://192.168.1.25:3001`. Keep the PostgreSQL and FastAPI host bindings on loopback.

The API image includes the repository-owned model artifact. Register the model version and metrics in `model_runs` before persisting predictions; `backend/bootstrap_product.py` performs that step for the native local cluster. For a separate deployment, use the values in `ml/evaluation/results.json` and preserve matching model versions. The service still returns estimates when an artifact exists but will not write a prediction against a missing registry version.

## Public deployment

Use an HTTPS reverse proxy or host-provided TLS in front of Next.js. Keep PostgreSQL and FastAPI on a private network. Set `APP_ENV=production`, disable `ENABLE_DEMO_LOGIN`, and set the identical explicit HTTPS `FRONTEND_ORIGINS` in API and frontend. In Compose, `AUTH_API_URL` is intentionally `http://api:8001` on the private service network; for a native frontend process, set it to the private API address. Preserve the original Host and Origin at the proxy; untrusted cross-origin writes are rejected. Never use `0.0.0.0` as a browser origin; it is a listen address, not the public site URL.

Provision credentials outside source control. Configure PostgreSQL backups, TLS where needed, resource limits, a trusted edge rate limiter and operational monitoring. The runtime currently has product-level table grants and enforces end-user roles in FastAPI; do not expose database credentials directly to browsers. Public demo deployments need separate synthetic-only data/accounts and an explicit access policy; the production configuration deliberately rejects open demo-login mode.

The repository has an origin remote, but no public push, hosting account changes, paid resources or DNS modifications were performed during this delivery. Host binding alone does not publish the app on the internet; a reachable machine, firewall rules, DNS and HTTPS termination are still required.

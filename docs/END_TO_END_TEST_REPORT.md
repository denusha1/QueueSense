# QueueSense staging integration test report

## Test boundaries

On 27 November 2026, verification used isolated PostgreSQL schemas and disposable containers with synthetic data. The frontend tests exercise the clinic browser path through Next.js and FastAPI. The HTTPS tests exercise the partner origin's Nginx, FastAPI and PostgreSQL path using a synthetic client certificate and signing keys. The actual managed gateway and Developer Portal require a separate hosted verification run.

## Results confirmed locally

| Scenario | Evidence |
| --- | --- |
| Frontend production build and private API connection | Next.js production build and TypeScript passed. Eight Chromium 1243 scenarios passed against the private API with pooling enabled. |
| Patient registration, token issuance and tracking | Receptionist registered a synthetic patient, issued a token, and retrieved it through the browser. A second active token returned 409. |
| Doctor and clinic RBAC | The assigned Doctor started and completed service, and an independent patient browser received both updates. Receptionist and Doctor were denied administration and a signed-out Doctor was denied queue access. |
| JWT and authorization | Backend tests covered missing, invalid, expired and revoked credentials. Browser tests covered cookie rotation, logout and denial after logout. |
| Quotas | FastAPI tests verified quota isolation, shared PostgreSQL accounting and 429 with `Retry-After`. All quota traffic targeted synthetic fixtures. |
| Container deployment and recovery | Full Compose build and health checks passed. Queue data survived PostgreSQL container replacement. A stopped PostgreSQL returned correlated 503 while liveness stayed healthy. Stopping FastAPI returned a correlated 503 from Next.js. Both services recovered after restart. |
| Container traffic limits and metrics | Tested absent and invalid JWTs, 429 through the frontend proxy, positive Retry-After and safe request correlation. Private Prometheus scraping required the generated bearer credential. Scrape output and application logs omitted the fixture JWT and tracking key. |
| Monitoring and application failures | Backend tests verified independent liveness, a sanitized 503 on database failure, metrics authentication, bounded route labels and correlated request logs. |
| Migrations and runtime role | All 18 migrations, replay, integrity and restricted runtime privileges passed in the native test run. |
| Partner HTTPS origin | Local Nginx required a synthetic client certificate, rejected missing and invalid assertions, verified a real HTTPS JWKS fetch, routed only the approved GET, returned 200 for the authorized aggregate, preserved origin 429 and Retry-After, and returned 504 during a stopped FastAPI upstream before recovering. |
| Release validation | All 150 backend tests passed. Both OpenAPI specifications passed validation. The API contract and Postman artifacts matched their generators. GitHub Actions syntax passed actionlint. |

## Hosted acceptance still open

- Real frontend and FastAPI addresses, managed PostgreSQL connectivity and TLS, deployment revision, database backup/restore, and health probes.
- Choreo Service and managed partner gateway connectivity, approved OAuth subscriber invocation, gateway rate limits, runtime metrics and alert delivery, and Developer Portal visibility and subscription.
- Production promotion and external publication approval.

The Choreo Console previously reported that creation of new organizations was restricted. A read-only CLI recheck in both regions reported that the session was unauthenticated. Hosted verification requires signing into an approved organization with an existing project or receiving authorized onboarding access. The repository contains no verified hosted gateway invocation or portal address.

## Repeat local verification

```sh
.venv/bin/python -m backend.verify_local
.venv/bin/python scripts/smoke_compose.py --faults
docker build -f backend/Dockerfile -t queuesense-stage19-api:local .
.venv/bin/python scripts/smoke_gateway_tls.py --image queuesense-stage19-api:local
```

JUnit reports and local runtime evidence are saved under `reports/stage19/`. Browser setup and report instructions are in [TESTING.md](TESTING.md). A live Development verification should follow [the gateway matrix](../api-management/gateway-testing.md) before promotion. The local and hosted acceptance records belong to distinct environments in the [deployment checklist](DEPLOYMENT_CHECKLIST.md).

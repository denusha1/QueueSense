# QueueSense enterprise readiness audit

Audited the tracked repository at commit `3dec54c` on 25 November 2026. The review covered application source, SQL migrations and grants, frontend routes and assets, synthetic data and model code, test suites, deployment and CI configuration, and project documentation. No live provider calls, external scans, cloud changes, or access to production patient data formed part of this review.

QueueSense is a functioning single-installation clinic queue application. Its strongest foundations are the PostgreSQL queue integrity rules, transactional service events and auditing, server-side staff permissions, and shared wait estimation. The enterprise work is to define a stable integration surface, harden existing trust boundaries, and measure behavior under realistic load before publishing any managed API.

## Existing behavior and evidence

| Area | Implemented behavior and evidence | Source |
| --- | --- | --- |
| Staff access | Four roles, Argon2id, opaque server-side sessions, logout/revocation, account settings, recovery and administrator TOTP enrollment. Backend tests cover role checks, account changes and fake-provider paths. | [App factory](../backend/app.py), [accounts](../backend/accounts.py), [auth tests](../backend/tests/test_auth.py), [account tests](../backend/tests/test_accounts_delivery.py) |
| Patient flow | Staff check-in produces a token and private QR. Appointments and walk-in QR check-ins reuse tokens on retry under their existing rules. Queue changes record events and update staff availability. Private status, feedback and notifications are scoped to the visit or booking. Backend tests cover core flow, concurrent numbering, QR retry, private-link boundaries and duplicate feedback. | [Queue](../backend/product.py), [arrivals](../backend/arrivals.py), [feedback](../backend/experience.py), [core tests](../backend/tests/test_core_queue.py), [arrival tests](../backend/tests/test_arrivals.py) |
| Clinicians | Staff records link to accounts and departments. Doctors can change queue state only for their linked clinician. Admins create staff, set schedules and update service/language profiles. Calling respects priority, compatibility and availability. Schedule editing/cancellation is absent from the registered API. | [Product](../backend/product.py), [planning](../backend/planning.py), [planning tests](../backend/tests/test_planning.py), [foundation schema](../database/migrations/001_foundation.sql) |
| Live updates and delivery | PostgreSQL notifications feed SSE with browser reconnect and polling fallback. Automation maintains reminders, delay warnings and inboxes. Opt-in SMTP, SMS and Web Push adapters are implemented and exercised with mocks. Real provider delivery was outside verification. | [SSE](../backend/arrivals.py#L183), [client hook](../frontend/components/live-updates.ts), [automation](../backend/automation.py), [delivery](../backend/delivery.py) |
| Wait estimates | Standard eligible queues use batch Random Forest inference with capacity fallback. Priority and constrained visits use a compatible-clinician workload estimate. The initial prediction, live estimate and actual wait have distinct meanings. The checked-in evaluation reports about 7.10 minutes MAE versus 9.62 for the baseline on synthetic held-out dates. This audit did not retrain or independently validate model quality on clinic traffic. | [Training](../ml/src/train.py), [results](../ml/evaluation/results.json), [prediction](../backend/services/prediction.py), [model monitoring](../backend/services/monitoring.py) |
| Analytics and reporting | Filtered queue metrics, peak hours, workload, forecasts, staffing simulations, feedback and alerts are implemented. CSV import supports dry runs, partial acceptance and duplicate detection. CSV/PDF report tests cover supported reports and formats. Historical imports assign service rows to the first department clinician, which can distort real clinician workload reporting. | [Metrics](../backend/services/metrics.py), [planning](../backend/planning.py), [importer](../backend/services/importer.py), [reports](../backend/services/reports.py), [operational tests](../backend/tests/test_operational.py) |
| Browser | Next.js App Router owns role workspaces, patient and self-arrival pages, same-origin API forwarding, and PWA behavior. The fresh production build and type check passed. Browser scenarios in the repository and historical test notes are separate from this audit's fresh checks. | [Workspace](../frontend/app/workspace/%5Brole%5D/page.tsx), [portal](../frontend/components/portal.tsx), [service worker](../frontend/public/sw.js), [historical results](TEST_RESULTS.md) |
| Data and operations | Twelve SQL migrations, restricted API database grants, three Dockerfiles, Compose, a three-job CI workflow, backup instructions and a small Locust scenario exist. | [Migrations](../database/migrations), [grants](../database/sql/product_runtime_grants.sql), [Compose](../docker-compose.yml), [CI](../.github/workflows/ci.yml), [backup runbook](BACKUP_RESTORE.md), [load report](LOAD_TEST.md) |

## Fresh local verification

| Check | Result |
| --- | --- |
| `.venv/bin/python -m backend.verify_local` | 66 passed. The verifier also checked native PostgreSQL migration replay, SQL integrity and runtime permissions. Two test-client deprecations and two Pydantic field alias warnings were emitted. |
| `.venv/bin/python -m unittest discover -s data/generator -p 'test_*.py' -v` | Seven passed. |
| `npm test --prefix database` | Passed all 12 migrations, seed totals, SQL/Python KPI parity, 11 integrity rejection cases and rollback in PGlite. |
| `npm run typecheck --prefix frontend` and `npm run build --prefix frontend` | Both passed. |
| `POSTGRES_PASSWORD=audit-placeholder docker compose --profile full config --quiet` | Compose configuration parsed. Image builds, container startup and health were outside this run. |
| FastAPI schema generation in process | 87 paths and 98 operations. The generated schema has no declared security schemes. |

Playwright, Locust, hosted CI and live provider delivery were not rerun in Stage 1. The committed [Locust evidence](LOAD_TEST.md) covers health and a single synthetic patient link on one local worker. It provides a historical baseline for that mix only. Cloud hosting, gateway policies, Developer Portal publishing and subscription are unverified external work.

## Gaps to address

- **External API.** The browser proxy and internal FastAPI surface already exist. The repository lacks an independently versioned and allowlisted integration API, JWT verification, documented client scopes, a curated OpenAPI artifact, and Choreo gateway, portal or subscription configuration. See [architecture and route inventory](EXISTING_ARCHITECTURE.md).
- **Security and privacy.** Database failure logging can include raw private-link paths. Existing limits vary by route and process, and account recovery has a provider-dependent timing discrepancy. Production configuration and staff read scope need explicit checks. See [technical debt](TECHNICAL_DEBT.md).
- **Scaling and operations.** Each SSE stream reserves a PostgreSQL connection, queue mutations and historical imports share a broad lock, and live predictions can be recalculated for the same department across many requests. Central metrics, tracing, a measured connection budget and evidence for a production rollout are missing. See [technical debt](TECHNICAL_DEBT.md).
- **Coverage.** CI runs one Chromium entry point while feature-focused scripts remain separately invoked. Gaps include proxy/API contract drift, concurrent shift overlaps, log redaction, sustained SSE load, delivery crash recovery, and installation from a complete container stack. See [technical debt](TECHNICAL_DEBT.md).
- **Documentation.** The backend README still describes recovery and MFA as absent, the architecture diagram describes five-second polling, and deployment verification statements differ across documents. Update those alongside the corresponding implementation stages. See [backend README](../backend/README.md), [existing system overview](architecture/system.md), [deployment](DEPLOYMENT.md), and [root README](../README.md).
- **Scope.** The schema separates departments inside one installation and has no organization or tenant ownership boundary. The working plan assumes a single clinic installation. Multi-tenant operation, SSO, configurable cross-clinic policy, and real-patient model validation require separate requirements or operational evidence.

## Preserve through the upgrade

- Keep existing browser routes, role workflows, cookie revocation, origin checks, and private patient/appointment links working during API evolution.
- Preserve priority/FIFO behavior, clinician eligibility, database constraints, atomic event and audit persistence, idempotent self-check-in, and restricted database privileges.
- Reuse shared inference, operational fallback, report cohort definitions, import validation, and the generator and test fixtures. Preserve the distinction between synthetic model evaluation and observed operational measurement.
- Keep the committed migrations immutable. Add forward migrations for integrity or performance changes and use existing regression tests to protect deployed data and behavior.

[Stage 2 and the sequenced implementation plan](IMPLEMENTATION_ROADMAP.md)

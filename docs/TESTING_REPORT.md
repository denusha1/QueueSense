# QueueSense final testing report

The portfolio verification on 28 November 2026 used synthetic data and the local repository checkout. Tests cover the clinic application and the dedicated partner origin. The managed Choreo gateway, Developer Portal and hosted GitHub Actions require separate acceptance.

| Area | Evidence | Scope |
| --- | --- | --- |
| Backend | 150 Pytest tests passed with PostgreSQL. | Sessions, JWT revocation, RBAC and resource ownership, concurrent check-in and token numbering, quotas, transactions, analytics, and request telemetry. |
| Database | All 18 migrations applied or replayed without checksum changes. | Native PostgreSQL checks verified runtime grants, integrity constraints and rollback. PGlite independently verified migration behavior in the earlier staging run. |
| Browser | Eight locked-Chromium scenarios passed. | Reception registration, duplicate rejection, token tracking, clinician service actions, admin analytics, responsive views, refresh/logout and proxy errors. |
| Generator | Seven reproducibility and data-integrity tests passed. | Synthetic arrivals, schedules, service intervals and summary consistency. |
| Portfolio assets | Nine Mermaid diagrams rendered successfully. Chromium read 127 seconds of video metadata from the WebM. | The README uses the existing local recording. The four-minute script is available for a new recording. |
| Frontend | Production build and TypeScript checks passed. ESLint reported 13 existing warnings, with 30 existing errors captured by its file-specific baseline. | The CI lint command enforces the file-specific suppression counts and the warning limit. |
| GitHub Actions | All workflow files passed actionlint. | Workflow syntax and expressions verified locally. |
| HTTP contracts | Both OpenAPI specifications passed validation. The OpenAPI and Postman drift checks passed. | Private staff preview and one-operation partner contract. |
| Docker | The isolated clinic stack passed the fault smoke. | Non-root app containers, readiness, persistence, JWT and HTTP 429, PostgreSQL and API outages, and recovery. |
| Partner origin | Local Nginx and FastAPI staging passed the HTTPS/mTLS and signed-assertion smoke. | Exact path and method, privacy-safe response, invalid assertion rejection, quota propagation and upstream recovery. This uses synthetic gateway credentials. |
| Observability | Private Prometheus scrape and safe request correlation passed locally. Promtool validated five alert rules and the scrape configuration. | Collector targeting and alert delivery in hosted environments require operational setup. |
| Performance | Locust completed 10, 50 and 100 user phases with no request errors. | One worker, local database, synthetic traffic and short phases. [Baseline and final measurements](PERFORMANCE_REPORT.md) |

## Run the relevant checks

```sh
.venv/bin/python -m backend.verify_local
npm run lint --prefix frontend
npm run build --prefix frontend
npm run typecheck --prefix frontend
npm test --prefix database
python3 scripts/smoke_compose.py --faults
```

The reproducible Chromium setup, fixture requirements, and JUnit reporting command are in [TESTING.md](TESTING.md). The final backend and browser JUnit files are in the local ignored `reports/stage20/` directory. Earlier staging artifacts and the exact release rehearsal commands are indexed in the [end-to-end report](END_TO_END_TEST_REPORT.md). [Historical verification](TEST_RESULTS.md)

## Pending acceptance

- GitHub-hosted pipeline execution and artifact delivery on an approved branch.
- Choreo Development Service and API Proxy rollout, real application subscription, gateway quota validation and Developer Portal visibility.
- Sustained performance with concurrent SSE streams, live delivery providers, and independent Firefox/WebKit coverage.

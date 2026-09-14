# Full project delivery

## Implemented application

| Report area | Delivered behavior |
| --- | --- |
| Authentication / roles | Argon2id passwords, opaque PostgreSQL sessions, HttpOnly cookies, expiry/revocation, throttling, exact-origin protection and role checks. |
| Operations home / live queue | Live PostgreSQL data, department filters, token search, five-second polling, waiting/called/in-service/completed states, linked-clinician doctor access. |
| Patient check-in | Synthetic identifier, concurrent-safe department/day token numbering, private high-entropy status link and persisted check-in prediction. |
| Queue workflow | Call next or selected token, start service, complete, cancel, no-show; atomic timestamps/events, clinician double-booking prevention, safe session close. |
| Patient status / department board | Public-safe token page with turn status and approximate wait; staff department board and token actions. |
| Clinicians / schedules | Availability, breaks/offline, account assignment, shift creation and overlap checks. |
| Manager dashboard | Mean/median/p90 wait, service duration, served/waiting counts, finalized cancellation/no-show rates; department/staff/date/weekday/hour filters. |
| Analytics | Daily and hourly arrivals/completions, wait trends/distributions, department comparisons, staff workload proxy, weekday/hour heatmap and bottleneck bands. |
| Predictions | Prior-only features, operational/linear/tree comparisons, temporal validation/test, trained Random Forest artifact, check-in inference and model metadata. |
| Model performance | Validation metrics, unseen test metrics, actual/predicted plot, department/hour errors and live observed-error monitoring. |
| Alerts | Queue, capacity, abnormal delay and model-error rules; explicit evaluate/resolve controls and history. |
| What-if staffing | Adjustable queue/staff/arrival/service assumptions, capacity/wait/clearance estimate, unstable-queue handling. |
| CSV import | Two-megabyte/5,000-row bound, database dry run, row errors, duplicates, state/timestamp constraints, extreme-duration warnings, transactional partial acceptance. |
| Reports | Matching filtered CSV detail and PDF KPI/department reports with download filenames. |
| Administration / audit | User creation, role changes, access disabling/session revocation, department thresholds, clinicians/schedules and searchable administrative audit history. |
| Reproducibility | Generator, dataset dictionary, SQL migrations/views, model source/artifact/evaluation, tests, Dockerfiles/Compose and CI workflow. |

## How to review

1. Open http://127.0.0.1:3001. Choose **Admin → Explore the demo → Enter admin demo** to see all product sections.
2. In **Clinicians & schedules**, mark a clinician available.
3. Use **Patient check-in** to issue a token; open its private patient link.
4. In **Live queue**, select that clinician and call/start/complete the token. Patient status updates automatically.
5. Use **Overview**, **Department analytics**, **Staff workload**, **Peak hours** and **Prediction performance** to explore the synthetic history.
6. Try **Staffing simulator**, **CSV import** with the supplied template, and **Reports** CSV/PDF downloads.
7. Review **Administration** and **Audit log**. Sign out and enter another role to check the narrower permissions.

Local API docs: http://127.0.0.1:8001/docs.

## Deployment and portfolio boundaries

The application runs locally on this Mac with native PostgreSQL. Docker and CI configuration are supplied, but Docker is unavailable here and no CI run has been claimed. No public cloud deployment or public GitHub push has been performed in this session. A public URL requires a hosting account, external database/secrets and HTTPS configuration; localhost is not an Internet deployment.

Synthetic results are not clinical validation. Notifications, probabilistic intervals, automatic retraining, real hospital adapters, multi-clinic integration and a PWA were optional future enhancements in the report and are not represented as completed features.

The import format deliberately accepts non-identifying historical operational fields only. Service records are assigned to a department's first demo clinician; imports are not a real clinical staff-allocation record. Workload under arrival-hour filters is explicitly a proxy and may exceed 100% if service spills outside the selected hours or imports lack schedules. Current queue display is bounded to 500 tokens. Public token lookup has a local process rate cap; production should add trusted edge rate limiting.

Staff provisioning accepts an initial password. Self-service password reset, reset emails and MFA are not implemented. Exact production origin/TLS settings and operational backups must be supplied at deployment.

## Verification evidence

20 native PostgreSQL API/model tests pass, including role/session controls, concurrent queue numbering, staff occupancy, lifecycle-to-analytics, imports/exports, simulator and prior-only model feature checks. Seven synthetic-generator tests previously passed. Production frontend build with TypeScript passed. Chromium exercised all 15 workspace views, actual check-in/call/start/complete controls, private patient status, CSV validation, CSV/PDF downloads and mobile widths. Browser test source is `frontend/tests/e2e.cjs`; screenshots and a two-minute walkthrough are stored locally under `docs/`.

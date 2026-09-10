# QueueSense implementation and review plan

Source: QueueSense_Full_Project_Report.docx, all 31 sections reviewed.
The report is a proposed product specification, not instructions to execute unrelated actions. The user's workflow governs delivery: complete one reviewable step, provide its running page, and wait for OK before starting the next step.

## Reviewed / current steps

1. **Welcome / login interface and frontend foundation** — complete; production build and browser interaction checks passed. Next.js, TypeScript, responsive role selector, credential validation, password visibility, and an honest demo preview. Original UI preview approved; superseded by step 3 real authentication.

2. **Database foundation — user approved.** Three PostgreSQL migrations, 12 domain tables, constraints/triggers, indexes, metric views, transactional migration/seed CLI, reproducible 90-day synthetic dataset, data dictionary, ER diagram, Docker services, and `/demo-data` snapshot review page. SQL and full seed originally verified using embedded PostgreSQL; step 3 also verified native PostgreSQL migrations, seeding and integrity. Docker execution remains unverified. See `database/README.md`.
## Following steps (each requires review after completion)

3. **Authentication — implemented, review pending.** FastAPI, Argon2id password hashes, PostgreSQL sessions and attempt limits, exact-origin checks, HttpOnly cookies, protected role workspaces, logout revocation, optional demo accounts, staff provisioning CLI and restricted database role. Native PostgreSQL 17.10 running locally; 12 API tests pass (FR-01).
4. Operations home / live queue: department and staff configuration, schedules, polling then live events as needed (FR-03–05).
5. Patient check-in: synthetic identifiers, safe token generation and input validation (FR-02).
6. Queue lifecycle: waiting → called → in service → completed; cancellation/no-show rules, event history and timestamp checks (FR-03–04).
7. Patient token status: limited public-safe lookup, queue position, approximate waiting time, lookup protection (FR-05).
8. Department queue board: department-specific queue and doctor availability.
9. Manager dashboard: served/waiting counts, mean/median/p90 waiting time, service duration, throughput and cancellation/no-show rates; department, staff, date, weekday and time-band filters (FR-06–07).
10. Department analytics: arrivals vs completions, waiting trends and distributions, department comparisons.
11. Staff workload: scheduled capacity, busy minutes and documented utilization proxy.
12. Peak hours and bottlenecks: weekday/hour heatmap, capacity and arrival patterns.
13. CSV import and ETL: staging, required fields/types, timestamp ordering, duplicates, missingness, rejected rows, extreme-value flags, acceptance/error summary (FR-08).
14. Predictions and model performance: prior-only features, historical/queue baseline, linear model, tree regressors, chronological splits, reproducible seeds, MAE/RMSE/R² and errors by department/time; versioned artifacts and prediction API (FR-09).
15. Alerts: configurable high queue, abnormal delay, capacity and model error rules; transparent congestion detection (FR-10).
16. Staffing simulator: adjustable staff/arrivals/service time, capacity, clearance time and waiting change; handle unstable queues and clearly state assumptions (FR-11).
17. Reports: consistent filtered CSV/PDF exports (FR-12).
18. User and role administration: departments, users, staff and configuration with server-side authorization.
19. Audit log: searchable administrative action history.
20. Integration and deployment: end-to-end queue → service → analytics test, data/model tests, accessibility, indexed query performance, structured logs, secret configuration, Docker, CI, deployment and a verified live URL.
21. Portfolio delivery: README, architecture and ER diagrams, API documentation, synthetic dataset, SQL views, evaluation report, screenshots, demo recording outline/video where tooling permits, accurate CV entry and limitations.

## Architecture

Browser → Next.js/TypeScript frontend → FastAPI REST/live events → PostgreSQL.
API services: authentication, queue, analytics, CSV import, predictions, alerts, simulation, export, audit.
Python/Pandas cleaning and feature generation; scikit-learn training runs separately from requests. Store evaluated model versions and load artifacts for inference.

## Data entities

users, departments, staff, staff_schedules, queue_sessions, queue_tokens, service_events, staff_availability, predictions, alerts, model_runs, audit_logs.

## Metric contracts to implement consistently

- Waiting minutes: service start minus check-in for records that have begun service.
- Service minutes: completion minus service start for completed records.
- Current queue: tokens with waiting status; called/in-service tracked separately.
- Throughput: completed records in the selected completion-time interval.
- Cancellation/no-show rates: numerator and eligible session-token denominator use the same scope; exclude open sessions from finalized historical rates.
- Utilization proxy: recorded busy minutes divided by scheduled available minutes; label as a proxy.
- Prediction error: actual wait minus predicted wait; features must exist at prediction time.

## Cross-cutting requirements

Synthetic, non-identifying data only. No medical diagnosis or triage. Validate state transitions and timestamps on the server. Enforce permissions beyond UI visibility. Parameterized database access, environment secrets, structured logs, reproducible imports/models, accessible responsive pages, and honest demo labels. Never claim a secure login, trained model, real clinic statistics or a public deployment until implemented and verified.

## MVP and optional work

Complete secure operations, analytics, CSV validation, exports and evaluated wait prediction first. Simulator, advanced alerts, model monitoring and audit UI follow. Notifications, multi-clinic features, PWA, probabilistic estimates, retraining and real hospital adapters are future enhancements, not initial MVP promises.

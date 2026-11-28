# Portfolio materials

For the final portfolio review, use the [internship contribution report](CHOREO_INTERNSHIP_CONTRIBUTION_REPORT.md), [four-minute script](DEMO_VIDEO_SCRIPT.md), and [technical interview guide](TECHNICAL_INTERVIEW_GUIDE.md).

## Project description

QueueSense is a full-stack patient-flow analytics platform that turns synthetic queue events into operational visibility. Next.js and FastAPI support role-specific check-in/service workflows, PostgreSQL enforces queue consistency, SQL powers filtered analytics, and an evaluated waiting-time model provides check-in estimates. It is an operational portfolio demonstration, not medical advice or a real hospital deployment.

## CV wording

- Built a Next.js/FastAPI/PostgreSQL patient-flow application with role-checked queue transitions, private token tracking, clinician scheduling and administrative audit history.
- Implemented filtered SQL analytics, validated synthetic CSV imports, CSV/PDF exports, congestion rules and a deterministic staffing simulator.
- Replayed historical events to build prior-only features and evaluated linear/tree regressors on chronological holdout data; the selected Random Forest achieved 7.10-minute MAE versus a 9.62-minute operational baseline on synthetic test visits.

- Designed a single-operation partner API for Choreo API Management. Implemented and verified the local HTTPS/mTLS origin, signed assertion checks, department scope, quota behavior and OpenAPI contract.
- Ran mixed synthetic Locust workloads at 10, 50 and 100 users. Measured a drop in aggregate p95 from 60 ms to 44 ms at 100 users and documented the token issuance p99 regression.

## Interview walkthrough

Explain the operational wait definition, transactional token numbering and staff occupancy, exact role/Origin checks, why queue states have different timestamp requirements, what makes the model evaluation leakage-aware, why simulator overload returns no finite clearance, and why synthetic performance does not establish real-clinic accuracy.

## Demo sequence

Welcome → admin demo login → overview/date filters → department and workload analysis → peak hours → model comparison → simulator → check-in → live token call/start/complete → private patient status → CSV validation/export → administration/audit → logout. Screenshots are under `docs/screenshots/`; the two-minute recording is `docs/demo/queuesense-walkthrough.webm`. Only synthetic demo data appears; no database credentials or real patient information is exposed.

## Reproducible local demo

Follow the setup in the root README and `docs/DELIVERY.md`. Start the configured local installation with `.venv/bin/python scripts/start_local.py`, then open `http://127.0.0.1:3001`. Choose **Admin → Explore the demo → Enter admin demo**. Demo entry is an explicit local convenience, not a published sample password; the generated demo account passwords are random and undisclosed. Public/production deployments must disable demo login. API docs are at `http://127.0.0.1:8001/docs` for local review only.

## Review materials and limits

- Walkthrough: [`docs/demo/queuesense-walkthrough.webm`](demo/queuesense-walkthrough.webm) (about two minutes).
- Screenshots: [`docs/screenshots/`](screenshots/) (live queue, analytics, mobile, model and appointment views).
- Architecture: [`docs/architecture/system.md`](architecture/system.md).
- Security findings and limits: [`docs/SECURITY_REVIEW.md`](SECURITY_REVIEW.md).
- Backup/restore procedure: [`docs/BACKUP_RESTORE.md`](BACKUP_RESTORE.md).
- Staff/student usability session plan: [`docs/USABILITY_REVIEW.md`](USABILITY_REVIEW.md). Participant feedback is still pending; no user study is claimed.

The walkthrough and screenshots show synthetic local data. No cloud URL or production deployment is currently claimed. Individual CV claims should identify the author's actual contribution; the repository alone cannot establish which parts were individually implemented.

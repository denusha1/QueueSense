# Portfolio materials

## Project description

QueueSense is a full-stack patient-flow analytics platform that turns synthetic queue events into operational visibility. Next.js and FastAPI support role-specific check-in/service workflows, PostgreSQL enforces queue consistency, SQL powers filtered analytics, and an evaluated waiting-time model provides check-in estimates. It is an operational portfolio demonstration, not medical advice or a real hospital deployment.

## CV wording

- Built a Next.js/FastAPI/PostgreSQL patient-flow application with role-checked queue transitions, private token tracking, clinician scheduling and administrative audit history.
- Implemented filtered SQL analytics, validated synthetic CSV imports, CSV/PDF exports, congestion rules and a deterministic staffing simulator.
- Replayed historical events to build prior-only features and evaluated linear/tree regressors on chronological holdout data; the selected Random Forest achieved 7.10-minute MAE versus a 9.62-minute operational baseline on synthetic test visits.

## Interview walkthrough

Explain the operational wait definition, transactional token numbering and staff occupancy, exact role/Origin checks, why queue states have different timestamp requirements, what makes the model evaluation leakage-aware, why simulator overload returns no finite clearance, and why synthetic performance does not establish real-clinic accuracy.

## Demo sequence

Welcome → admin demo login → overview/date filters → department and workload analysis → peak hours → model comparison → simulator → check-in → live token call/start/complete → private patient status → CSV validation/export → administration/audit → logout. Screenshots are under `docs/screenshots/`; the two-minute recording is `docs/demo/queuesense-walkthrough.webm`. Only synthetic demo data appears; no database credentials or real patient information is exposed.

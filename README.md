# QueueSense

A full-stack patient-flow and waiting-time analytics application built with Next.js, TypeScript, FastAPI, PostgreSQL and scikit-learn. It connects synthetic check-in/service events to queue visibility, filtered operational analytics and evaluated waiting-time estimates. It is not a clinical decision system.

## Open the application

**Local app:** http://127.0.0.1:3001 · **API docs:** http://127.0.0.1:8001/docs

Choose **Admin → Explore the demo → Enter admin demo** for all features. Reception and Doctor focus on queue operations; Manager has analytics and planning access. All clinic data is synthetic.

The full workspace includes live queue, patient check-in/status, department queue board, clinician availability/schedules, manager analytics, department/workload/peak-hour analysis, model performance, staffing simulation, alerts, CSV import, CSV/PDF reports, user/department administration and audit history. See the [delivery matrix and review guide](docs/DELIVERY.md).

## Premium interface

The shared visual system now uses an ink-and-teal navigation shell, layered hero artwork, locally hosted DM Sans/Manrope typography, clearer metrics, responsive forms and tables, and consistent appointment, QR and patient screens. Chart legends let you show or hide a series while preserving at least one visible series. Charts also support arrow-key exploration.

Pointer lighting, floating line art, chart-bar entrances, dialog transitions, scroll progress and a keyboard-friendly back-to-top control provide subtle interaction feedback. Reduced-motion preferences disable decorative animation and pointer effects. Local font files and their OFL licenses live under `frontend/public/fonts`, eliminating runtime Google Fonts requests.

Run `node frontend/tests/premium-ui.cjs` with the local app running to verify chart controls, keyboard focus, motion preferences, mobile navigation and all 16 workspace views at 375, 768 and 1440 pixels.

## Workspace enhancements

Use **⌘/Ctrl K** to search the pages available to your role. **Compact** saves a denser layout in this browser; **Focus** hides navigation while retaining workspace search. Live queue and department board support status filtering, token search and sorting by arrival, token or estimated wait.

Analytics includes quick date ranges and an operational pulse showing completion rate, the department with the longest average wait, and departments within a selectable average-wait target. These indicators use the selected cohort; the target is a local planning control. Updated styling includes responsive toolbars, keyboard focus states and reduced-motion support.

Run `node frontend/tests/workspace-tools.cjs` with the local app running to check the new interactions and responsive layouts.

## Appointments, QR arrivals and live updates

Admin and Reception can open **Appointments**, publish half-hour arrival slots (1–20 places, up to 90 days ahead), book a place, cancel a booking and share its private QR link. Check-in opens 30 minutes before the slot and closes 30 minutes after it starts. Arrival slots reserve check-in capacity, not clinician time; checked-in appointments join the ordinary FIFO queue.

In **Patient check-in → Generate today’s QR**, select a department to create a walk-in poster link. It expires at midnight in Asia/Colombo and can be revoked immediately. Patients scan, confirm arrival and open their private token page. Repeating an appointment check-in retrieves the same token; walk-in retry protection uses a browser-stored request ID and an atomic database record. The same browser reuses its token for that department QR; reception can issue an additional legitimate visit. Walk-in QR submissions are limited to 20 new arrivals per minute per code.

Live queue, department board, clinician availability and patient status now receive server-sent events (SSE) after committed database changes. A reconnect refresh reconciles missed changes; a 15-second polling fallback runs while the stream is unavailable. Streams reconnect periodically to revalidate staff sessions. Event payloads contain no patient details or token links. The Next.js proxy forwards streams without buffering.

**Local QR limitation:** `127.0.0.1` links work on this computer. Phone scanning requires a reachable deployed clinic URL configured in `FRONTEND_ORIGINS`; QR generation accepts only configured origins.

After updating an existing installation, run `.venv/bin/python -m backend.bootstrap_product`, rebuild the frontend and restart the local API/frontend. Migration `006_arrivals_realtime.sql` adds booking/check-in tables and PostgreSQL notification triggers; no extra package is required.

Validation: `.venv/bin/python -m backend.verify_local` and, with the app running, `node frontend/tests/arrivals.cjs`. The latter checks booking capacity, QR rendering, anonymous arrivals, retry protection, queue/patient pushes between independent browser sessions, revocation and mobile layouts.

## Start the existing local installation

```sh
.venv/bin/python scripts/start_local.py
```

The native PostgreSQL cluster runs privately on port 55432 with random credentials stored only under ignored `.local/`. The API runs on 8001 and frontend on 3001. Restart API/frontend after code or model changes.

## Fresh local setup

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
npm ci --prefix frontend
python3 data/generator/generate.py
.venv/bin/python ml/src/train.py
# Install PostgreSQL 17; set POSTGRES_BIN if it is outside the default Homebrew path.
.venv/bin/python -m backend.local_setup
.venv/bin/python -m backend.bootstrap_product
npm run build --prefix frontend
.venv/bin/python scripts/start_local.py
```

On Apple Silicon this workspace uses portable native PostgreSQL binaries installed with `npm install --prefix .local/pg-runtime @embedded-postgres/darwin-arm64@17.10.0-beta.17`; the setup helper detects them automatically. The failed Homebrew download is not needed to run the application.

See [backend configuration](backend/README.md) and [database setup](database/README.md). No production secrets or personal patient records are committed.

## Data, models and verification

The reproducible seed contains 15,265 fictional visits across 90 calendar days, three departments and nine clinicians. Current demo visits add to this baseline. Data dictionary: [data/data_dictionary.md](data/data_dictionary.md).

The selected Random Forest achieves **7.10-minute MAE** on unseen chronological synthetic test data versus **9.62 minutes** for the queue-rate baseline. [Model methodology and limitations](ml/README.md), [evaluation results](ml/evaluation/results.json).

```sh
python3 -m unittest discover -s data/generator -p 'test_*.py' -v
.venv/bin/python -m backend.verify_local
npm run build --prefix frontend
# With the local app running; install Chromium once with npx playwright install chromium.
npm run test:e2e --prefix frontend
```

Verification includes native PostgreSQL migrations/seed/integrity, concurrent token numbering, staff occupancy, role/session controls, lifecycle-to-analytics, import dry-run/errors/duplicates, PDF/CSV output, simulator edges and feature-leakage checks. Chromium checks cover all 15 workspace views, check-in through completion, patient status, forms and responsive layouts. Screenshots: [docs/screenshots](docs/screenshots).

## Architecture and deployment

[System architecture](docs/architecture/system.md) · [ER diagram](docs/architecture/database.md) · [Portfolio wording](docs/PORTFOLIO.md) · [Deployment guide](docs/DEPLOYMENT.md).

Dockerfiles, Compose services and a GitHub Actions workflow are supplied. Docker/CI are not executed here. **The running link is local, not a public deployment.** Cloud hosting, public DNS/HTTPS and a production database must be configured externally before a public release. Optional notifications, real hospital integrations, probabilistic intervals and automatic retraining remain future enhancements.

## Demo recording

[Two-minute synthetic-data walkthrough](docs/demo/queuesense-walkthrough.webm).

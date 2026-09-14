# QueueSense

A full-stack patient-flow and waiting-time analytics application built with Next.js, TypeScript, FastAPI, PostgreSQL and scikit-learn. It connects synthetic check-in/service events to queue visibility, filtered operational analytics and evaluated waiting-time estimates. It is not a clinical decision system.

## Open the application

**Local app:** http://127.0.0.1:3001 · **API docs:** http://127.0.0.1:8001/docs

Choose **Admin → Explore the demo → Enter admin demo** for all features. Reception and Doctor focus on queue operations; Manager has analytics and planning access. All clinic data is synthetic.

The full workspace includes live queue, patient check-in/status, department queue board, clinician availability/schedules, manager analytics, department/workload/peak-hour analysis, model performance, staffing simulation, alerts, CSV import, CSV/PDF reports, user/department administration and audit history. See the [delivery matrix and review guide](docs/DELIVERY.md).

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

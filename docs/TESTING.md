# QueueSense automated testing

Run all tests with generated synthetic data. Use a disposable database or the dedicated local test cluster. The browser suite creates synthetic accounts, patients, departments and queue tokens.

| Journey or API behavior | Coverage |
| --- | --- |
| Reception registers a patient, issues a token and manages the queue | [Browser role journey](../frontend/tests/role-journey.cjs), [registration and concurrency tests](../backend/tests/test_patient_identity.py) |
| A patient validates a token link and tracks their own queue entry | [Browser role journey](../frontend/tests/role-journey.cjs), [priority and tracking suite](../frontend/tests/core-queue.cjs), [resource checks](../backend/tests/test_authorization.py) |
| An assigned doctor starts and completes the visit | [Browser role journey](../frontend/tests/role-journey.cjs), [queue integration tests](../backend/tests/test_product.py) |
| An administrator views analytics and exports data | [Admin end-to-end suite](../frontend/tests/e2e.cjs), [operational browser suite](../frontend/tests/operational.cjs) |
| Staff sign in, renew, sign out and lose access | [JWT backend tests](../backend/tests/test_jwt_auth.py), [browser cookie and session suite](../frontend/tests/jwt-session.cjs) |
| REST success and errors for missing, invalid or expired JWTs, permissions and missing resources | [Backend API tests](../backend/tests/), [browser proxy errors](../frontend/tests/api-errors.cjs) |
| Duplicate and concurrent queue operations, rate limits and retry headers | [Patient and queue concurrency tests](../backend/tests/test_patient_identity.py), [traffic tests](../backend/tests/test_traffic.py) |
| PostgreSQL schema, seed integrity, migration replay and runtime privileges | [Native PostgreSQL verifier](../backend/verify_local.py), [PGlite migration runner](../database/tests/verify.mjs), [Compose smoke](../scripts/smoke_compose.py) |

## Run locally

For native PostgreSQL setup, follow [DEPLOYMENT.md](DEPLOYMENT.md). After creating the isolated local database and synthetic data, run:

```sh
mkdir -p reports
.venv/bin/python -m unittest discover -s data/generator -p 'test_*.py' -v
npm test --prefix database
PYTEST_ADDOPTS=--junitxml=reports/backend.xml .venv/bin/python -m backend.verify_local
```

Install the frontend packages and locked Chromium revision. Start the synthetic app on the URL in `BASE_URL` with JWT signing, model assets and demo roles enabled. The CI frontend workflow provides the exact fixture provisioning sequence.

```sh
npm ci --prefix frontend
frontend/node_modules/.bin/playwright install chromium
npm run lint --prefix frontend
npm run build --prefix frontend
npm run typecheck --prefix frontend
BASE_URL=http://127.0.0.1:3001 node --test \
  --test-reporter=spec --test-reporter=junit \
  --test-reporter-destination=stdout --test-reporter-destination=reports/browser.xml \
  frontend/tests/suite.test.cjs
python3 scripts/smoke_compose.py
```

The browser suite runs sequentially because cases share synthetic clinic fixtures. CI uses `BROWSER_TEST_DATABASE_URL` to clear only the four seeded demo accounts’ traffic counters before each case. The fixture command requires a loopback test database or a dedicated `test_` schema. Application limits remain enabled during each case. For an equivalent local run, point that variable to your isolated fixture owner connection and set `QUEUESENSE_TEST_PYTHON=.venv/bin/python` when needed. Set `QUEUESENSE_SCREENSHOTS_DIR` to save screenshots elsewhere. The suite defaults to `reports/browser-screenshots`. The standalone script `npm run test:e2e --prefix frontend` still runs the original admin scenario.

See [TEST_RESULTS.md](TEST_RESULTS.md) for the recorded local run and [CICD_PIPELINE.md](CICD_PIPELINE.md) for GitHub artifacts. The CI browser suite covers Chromium. Firefox, WebKit, delivery providers and hosted Choreo behavior require separate verification. Some existing standalone browser scenarios cover optional features and need their own fixture settings before they can run in the shared suite.

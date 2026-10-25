# 100-user load test

## Result

Run on 25 October 2026 against the local synthetic-data PostgreSQL cluster, with one QueueSense API worker on macOS Apple Silicon. Locust 2.47 ramped to 100 virtual users at 10 users/second, then ran for three minutes. The scenario mixed `/health` and `/patient/:key` at a 1:4 task ratio, with 12–18 seconds between requests. It sent 1,203 requests: **0 failures**, 6.73 requests/second overall, 23.4 ms average response time, 57 ms aggregate p95, and 130 ms max. Patient status: 974 requests, 24.3 ms average, 60 ms p95, 130 ms max.

This verifies the single local API process and local database for that request mix. It does not prove a production or multi-worker capacity target, and it does not exercise the Next.js frontend, SSE streams, authenticated manager dashboards, or external delivery providers. Results are hardware-, data- and configuration-specific.

## Rate-limit observation

An initial aggressive run with 1–3 second waits produced 7,118 patient-status requests and 5,318 HTTP 429 responses (74.7% of those requests). This is expected from the current **600 public token reads/minute per API process** protection. The committed Locust scenario uses 12–18 second waits and the passing workload remained below that threshold. A test that removes or bypasses this guard would not represent the deployed behavior.

## Reproduce locally

Make sure the local PostgreSQL installation has synthetic demo data, install the Locust extra, then run:

```sh
.venv/bin/pip install -r loadtests/requirements.txt
.venv/bin/python scripts/run_local_loadtest.py
```

The runner starts a temporary API worker on `127.0.0.1:8013`, obtains a synthetic patient key from the local database without printing it, runs Locust, and stops that worker. CSV output and the temporary API log are written under ignored `.local/loadtest/`.

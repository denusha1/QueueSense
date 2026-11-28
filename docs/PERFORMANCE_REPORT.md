# QueueSense mixed-workload performance

On 26 November 2026, the local benchmark ran 10, 50 and 100 concurrent virtual users against one FastAPI worker on macOS 15.6.1 (Apple Silicon) and loopback PostgreSQL. The baseline opened a new database connection for each unit of work. The final run used a pool capped at eight connections, narrower analytics queries, and a queue query that uses the requested department and skips fetching rows when the requested page is empty. Both runs used the same synthetic fixture design and kept the application's quotas enabled. Per-request logs and Prometheus collection were disabled for this comparison.

## Method

[Locust scenario](../performance/locustfile.py) · [Isolated runner](../performance/run.py) · [Comparison generator](../performance/compare.py)

Each phase created a fresh PostgreSQL schema seeded with 90 calendar days of synthetic history, generated unique staff accounts and signed short-lived test JWTs, and added active and completed patient links. Forty percent of users polled patient status. Twenty percent registered patients and then issued tokens. Twenty percent used the paginated doctor queue, ten percent rotated among the three v1 analytics endpoints, and ten percent checked their authenticated profile. Users waited 6–10 seconds between operations. Locust ramped over roughly four seconds and reset its request counters at the end of the ramp. Each full phase lasted 40 seconds.

CPU and RSS were sampled for FastAPI once per second after ramp-up. PostgreSQL sampling counted current sessions, active sessions and sessions waiting on locks with the fixture's application name. Sampling can miss short-lived sessions and lock waits. Raw request CSVs, sampling JSON, and logs are under the ignored `reports/performance/` directory.

## Baseline and final results

| Users | Run | Requests | Req/s | Mean ms | P50 ms | P95 ms | P99 ms | Error rate | Mean API CPU % | Peak API MiB | Peak DB sessions | Peak active DB | Lock waits sampled |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10 | Baseline | 53 | 1.53 | 37.6 | 37 | 73 | 76 | 0.0% | 2.7 | 148.1 | 0 | 0 | 0 |
| 10 | Final | 51 | 1.50 | 18.1 | 15 | 50 | 55 | 0.0% | 1.1 | 166.7 | 3 | 0 | 0 |
| 50 | Baseline | 256 | 7.31 | 35.7 | 31 | 75 | 130 | 0.0% | 10.2 | 200.9 | 1 | 1 | 0 |
| 50 | Final | 256 | 7.29 | 15.7 | 13 | 37 | 50 | 0.0% | 4.2 | 182.8 | 8 | 1 | 0 |
| 100 | Baseline | 521 | 14.85 | 32.2 | 26 | 60 | 150 | 0.0% | 17.2 | 225.1 | 1 | 1 | 0 |
| 100 | Final | 519 | 14.94 | 15.2 | 12 | 44 | 58 | 0.0% | 7.3 | 164.3 | 8 | 1 | 0 |

| Run | Operation at 100 users | Requests | Req/s | Mean ms | P50 ms | P95 ms | P99 ms | Error rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | `GET /api/v1/analytics/peak-hours` | 15 | 0.43 | 49.8 | 47 | 67 | 67 | 0.0% |
| Baseline | `GET /api/v1/analytics/queue-performance` | 16 | 0.46 | 54.7 | 47 | 150 | 150 | 0.0% |
| Baseline | `GET /api/v1/analytics/waiting-time` | 15 | 0.43 | 55.4 | 48 | 160 | 160 | 0.0% |
| Baseline | `POST /api/v1/patients` | 87 | 2.48 | 31.7 | 24 | 48 | 150 | 0.0% |
| Baseline | `GET /api/v1/queue` | 85 | 2.42 | 33.4 | 26 | 74 | 160 | 0.0% |
| Baseline | `POST /api/v1/queue` | 87 | 2.48 | 34.0 | 32 | 47 | 77 | 0.0% |
| Baseline | `GET /auth/me` | 43 | 1.23 | 22.3 | 17 | 36 | 120 | 0.0% |
| Baseline | `GET /patient/{key}` | 173 | 4.93 | 27.8 | 21 | 45 | 150 | 0.0% |
| Final | `GET /api/v1/analytics/peak-hours` | 14 | 0.40 | 39.0 | 44 | 51 | 51 | 0.0% |
| Final | `GET /api/v1/analytics/queue-performance` | 15 | 0.43 | 32.6 | 35 | 62 | 62 | 0.0% |
| Final | `GET /api/v1/analytics/waiting-time` | 14 | 0.40 | 35.0 | 35 | 60 | 60 | 0.0% |
| Final | `POST /api/v1/patients` | 86 | 2.48 | 11.6 | 9 | 18 | 58 | 0.0% |
| Final | `GET /api/v1/queue` | 87 | 2.50 | 13.2 | 11 | 49 | 58 | 0.0% |
| Final | `POST /api/v1/queue` | 86 | 2.48 | 18.4 | 17 | 25 | 120 | 0.0% |
| Final | `GET /auth/me` | 43 | 1.24 | 8.8 | 6 | 13 | 43 | 0.0% |
| Final | `GET /patient/{key}` | 174 | 5.01 | 12.9 | 11 | 35 | 54 | 0.0% |

## Findings

At 100 users, mean latency fell from 32.2 ms to 15.2 ms, p95 from 60 ms to 44 ms, and p99 from 150 ms to 58 ms. Throughput stayed near 15 requests per second because the workload used think time. Error rate was zero in every phase. Average API CPU fell from 17.2% to 7.3% at 100 users. The pool kept up to eight database sessions open in the busier phases and used more memory than the baseline at 10 users. Token issuance alone had a worse p99 at the 100-user level, 120 ms versus 77 ms, despite lower mean and p95. Those tails and the per-endpoint analytics percentiles come from small request counts.

Authentication, authorization and quota accounting still run on each request. Before pooling, they opened connections independently of the business query. The pool bounds reuse per FastAPI worker and resets the read-only and repeatable-read defaults after a paginated snapshot. SSE subscriptions keep their dedicated PostgreSQL sessions. The v1 analytics endpoints no longer compute aggregates discarded by their response schema. Department-filtered queue reads can use the existing department/date session key; no additional indexes were added for this workload. A page that has no rows skips the second query. Queue and authorization results remain uncached so changes and session revocations are visible immediately.

A separate PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` check on the 90-day synthetic cohort took the median of seven warmed executions. The full analytics projection took 32.1 ms, compared with 21.2 ms for waiting time and 19.8 ms for queue performance. The department-filtered queue count went from 16 to 9 shared buffer hits and from 0.090 ms to 0.068 ms. This was a focused count-query check with an explicit service date. It did not reproduce all API work or doctor filters. The readings are in `reports/performance/query-plans.json`.

The measured effect covers the combined pool and query changes. One short experiment per configuration and load level cannot isolate each change or establish production capacity. Network, Next.js, the hosted gateway, larger historical cohorts, SSE concurrency and sustained load remain outside this benchmark. A production sizing decision needs a longer staging run with separate database resource monitoring and enough observations per endpoint to characterize tail latency.

The final portfolio review kept these measured runs as the performance evidence and reran the application regression tests separately. [Final testing report](TESTING_REPORT.md)

## Reproduce

Install the [local synthetic PostgreSQL environment](DEPLOYMENT.md) and the locked Locust extra. The runner starts its own API on a free loopback port. It accepts only 10, 50 or 100 users and uses fresh disposable schemas. There is no argument for a remote load target.

```sh
.venv/bin/pip install -r backend/requirements.lock -r loadtests/requirements.txt
.venv/bin/python performance/run.py --output reports/performance/final --seconds 40 --pool 8
.venv/bin/python performance/compare.py reports/performance/baseline reports/performance/final
```

The recorded baseline used the repository API before the query changes, with `--pool 0`. Running the current version with zero compares pooling alone because the query improvements remain active.

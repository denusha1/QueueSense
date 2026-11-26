# QueueSense traffic management

## Backend budgets

The origin uses PostgreSQL counters shared across FastAPI replicas. Apply migration 018 before deploying this code. The existing process-local sliding window guards public capability requests before database lookup. Login, recovery and kiosk issuance retain their existing safeguards.

| Traffic | Subject | Read limit per minute | Write limit per minute |
| --- | --- | ---: | ---: |
| Patient tracking or appointment link | UUID of the visit or appointment resolved from its private link | 40 | 12 |
| Active shared kiosk link | Kiosk UUID | 120 | 60 |
| Receptionist | Authenticated staff account | 240 | 120 |
| Doctor | Authenticated staff account | 180 | 60 |
| Administrator | Authenticated staff account | 180 | 60 |
| Manager | Authenticated staff account | 120 | 30 |
| Specific administration, audit, export and import routes | Authenticated account in a separate budget for these operations | 60 | 30 |
| Partner weekly report | Department assigned to the verified proxy context | 30 | — |

The per-process guard accepts up to 600 requests in a rolling minute across `/patient/` and `/self-checkin/`, including unknown links. Keys that resolve to an actual object additionally share the database budgets above across all routes for that object. Current patients authenticate using an object-specific private link. The same patient can hold separate links for different visits or appointments. Reception can sustain higher request rates because it handles interactive desk operations. Admin routes still require the relevant permissions after admission. [Role matrix](ROLE_PERMISSION_MATRIX.md)

Login uses its existing 15-minute database counters for the account and immediate backend peer. Behind Next.js the peer is shared. Recovery and MFA use their existing workflow-specific throttles. Walk-in issuance still has a 20-new-arrivals-per-minute cap per kiosk. A kiosk retry with the same request ID can return its existing receipt if the request reaches the operation.

## Enforcement and measurement

- A PostgreSQL statement admits or denies a request atomically using a database-clock minute boundary. Reads and writes have independent counters. Staff budgets count requests authenticated successfully, including later authorization or validation failures. Link budgets start once the capability resolves. The partner budget counts requests that pass assertion, department and week checks. Accepted traffic spends its quota even if the business action later fails.
- Usage can spike around the minute boundary. These are request counts and provide no concurrent connection limit. SSE requests consume a quota on connection or reconnect. Capacity and stream concurrency should be measured at the ingress and database.
- Counters store the policy, internal UUID, window, and accepted request count. The automation worker removes records older than a day in batches of up to 1,000 and skips locked rows. If automation is disabled on all replicas, schedule housekeeping before long-running use. Monitor table size and lock latency. For high traffic, measure the cost of per-request database writes before raising limits.
- The anonymous process ceiling is shared by traffic reaching one worker and multiplies with replicas. It is a fallback for unknown links and can affect legitimate users during a concentrated flood. An upstream distributed per-client or aggregate limiter should absorb that traffic before FastAPI. Use trusted ingress-provided identity for any per-client policy. QueueSense does not trust caller-provided forwarding headers.
- Report total requests, HTTP 429 or 5xx by operation and environment, response latency and repeat successes after a reset. The counter table only records admitted requests for the current stored window. Count rejected requests at the ingress or gateway. Avoid log labels containing private links, credentials or user/department identifiers.

## HTTP 429 and retry behavior

QueueSense returns the stable error code `rate_limited` and usually an integer `Retry-After` in seconds. The per-minute distributed budgets return the seconds remaining in that window. Login and recovery may return a longer delay. Next.js forwards the origin header.

- Show the wait to the caller. When retrying a safe read, wait at least `Retry-After` and add jitter for automated callers. Without a usable header, use bounded exponential backoff and stop after a small number of attempts.
- Reconcile the current server state before retrying check-in, booking, or other mutations. For kiosk arrivals, reuse the original request ID. Do not automatically retry sign-in or administrative mutations.
- Choreo may reject before QueueSense receives the request. Treat its response shape separately. Gateway policy values and status behavior remain pending live verification. [Choreo policy and verification](../api-management/rate-limiting.md)

[Traffic regression tests](../backend/tests/test_traffic.py) cover simultaneous requests through independent connections, resets, `Retry-After` and staff and patient-link quota isolation. The existing security suite covers the process guard.

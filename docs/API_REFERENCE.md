# QueueSense v1 REST API reference

Base path `/api/v1`. These routes are a private staff contract on FastAPI. The current Next.js workspaces continue using their existing browser routes and response shapes. Keep the internal FastAPI service private. The future Choreo integration has a separate exposure policy and contract. [API architecture](API_ARCHITECTURE.md)

The running application exposes OpenAPI at `/openapi.json` and interactive documentation at `/docs`. Apply migrations through 016 and reapply the [authentication](../database/sql/auth_runtime_grants.sql) and [product](../database/sql/product_runtime_grants.sql) runtime grants before deploying this version.

## Authentication and responses

Staff log in using their email, password and selected role. Include `otp` when
the account requires an authenticator code. With JWT enabled, the v1 login and
refresh responses include a short-lived `access_token` and `token_type: Bearer`
alongside the identity in `data`. The server also sets an HttpOnly access cookie
and an opaque HttpOnly refresh cookie. Secure applies in production. Protected
v1 requests can send the access cookie or `Authorization: Bearer <access JWT>`.
All writes require an exact configured `Origin`.

Refresh requires the refresh cookie and rotates it atomically without extending
the session's original expiry. A repeated logout returns 204 with an empty
body. Non-production instances without a signing secret retain the prior
opaque-cookie flow. [JWT token policy, validation and revocation](JWT_AUTHENTICATION.md)

A normal result uses `{"data": ...}`. Collections with paging also return `pagination`. Successful creation of a patient registration or queue token includes a relative `Location` header. The API sends `Cache-Control: no-store` and `X-Request-ID` with responses.
Use that request ID to find the corresponding server error event.

```json
{
  "data": [{"id": "d21804de-1be2-4c95-a25c-a70660eb8818", "external_id": "DEMO-101"}],
  "pagination": {"page": 1, "page_size": 25, "total": 1, "pages": 1}
}
```

Paging is one-based. The default page size is 25, the maximum is 100, and the highest allowed page number is 10,000. A page beyond the last returns an empty list with the requested page and the current totals. Empty results have zero total pages. Each page and count share one database snapshot. Later requests can reflect intervening writes. Use `direction=asc` or `desc` where listed. Dates take `YYYY-MM-DD`, timestamps include a timezone, and resource IDs are UUIDs.

## Endpoints

| Method and path | Access | Request and result |
| --- | --- | --- |
| `POST /auth/login` | Allowed origin | JSON `email`, `password`, `role`, optional `otp`. Returns 200 with staff identity, expiry, access token and cookies in JWT mode. |
| `POST /auth/refresh` | Valid refresh credential | Empty request. Returns 200 with identity and replacement credentials. |
| `POST /auth/logout` | Allowed origin | Empty request. Returns 204 and expires the cookie. |
| `GET /patients` | Admin or Reception | Paged registry sorted by `external_id` in `direction`. Optional `external_id` is an exact case-insensitive match. |
| `POST /patients` | Admin or Reception | JSON `external_id`. Returns 201 on first registration and 200 with the existing patient on repeat. |
| `GET /patients/{patient_id}` | Admin or Reception | Returns the patient UUID and clinic identifier, or 404. |
| `PATCH /patients/{patient_id}` | Admin | JSON `external_id`. Returns 200. Preserves the patient UUID and linked visits. Returns 409 when another patient owns that identifier. |
| `GET /queue` | Any staff role | Paged queue records. Filters `department_id`, `staff_id`, `status`, `day`. Defaults to each department's current clinic date. Sorts by `priority` (default), `arrival`, or `token`, with optional `direction`. Default priority sorting shows expedited visits first and preserves arrival order within a priority. |
| `POST /queue` | Admin or Reception | JSON `department_id`; optional `patient_id`, `priority_class`, `priority_reason`, `service_type`, `required_language`, `preferred_staff_id`, and `continuity_required`. Returns 201. Duplicate active visits for the linked patient return 409. |
| `GET /queue/{token_id}` | Any staff role | Returns the token number, department, assigned clinician, state, priority class and lifecycle timestamps. |
| `PATCH /queue/{token_id}` | Admin, Reception or linked Doctor | JSON `status`, with `staff_id` when calling a visit. Returns 200. The existing lifecycle, availability and clinician ownership checks apply. |
| `GET /queue/{token_id}/history` | Any staff role | Paged persisted events ordered by time and lifecycle order for ties. Includes `check_in`, `called`, `service_start`, and applicable completion, cancellation or no-show events. |
| `GET /doctors` | Any staff role | Paged clinicians, with optional `department_id` and `active` filters. Sorts by display name in `direction`, then by ID. |
| `GET /doctors/{doctor_id}` | Any staff role | Returns the doctor's ID, department, display name, active status and current availability. |
| `GET /doctors/{doctor_id}/schedule` | Any staff role | Paged shifts. Requires `start` and `end`. Optional `status` is `scheduled` or `cancelled`. Sorts by start time in `direction`, then by ID. |
| `GET /analytics/waiting-time` | Admin or Manager | Returns measured wait count, mean, median and 90th percentile in minutes. An unavailable measure is `null`. |
| `GET /analytics/peak-hours` | Admin or Manager | Returns up to 168 populated weekday/hour buckets in weekday and hour order. Each bucket reports arrivals and mean measured wait. |
| `GET /analytics/queue-performance` | Admin or Manager | Returns cohort arrivals, completed, waiting, cancelled and no-show counts, average service duration, and cancellation/no-show rates for closed sessions. |

All paths in the table are relative to `/api/v1`. Analytic queries require inclusive `start` and `end` dates. Optional filters are `department_id`, `staff_id`, `weekday` (ISO 1–7), `hour_from` and `hour_to` (0–23). Date bounds may be at most 366 days apart. Aggregation uses the existing arrival-date cohort and department-local hours. Rate values are percentages. [Shared SQL metrics](../backend/services/metrics.py)

Clinic identifiers are normalized to uppercase and validated against the clinic identifier format. Access to the registry is restricted. Queue responses omit private patient links, patient identifiers and free-text priority reasons. Protect cookie headers and registry filter values when configuring access logs and telemetry.

## Error contract

```json
{
  "success": false,
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": [{"field": "query.page_size", "code": "less_than_equal"}]
  },
  "request_id": "fcba5560-75b5-4c6b-8bd3-0ea4c8ee5d72"
}
```

| Status | Meaning |
| --- | --- |
| 400 | Malformed JSON or an invalid operation request. |
| 401 | Session or credentials are invalid, expired or revoked. |
| 403 | Origin, staff role, permission or clinician ownership check failed. |
| 404 | Resource or route is absent. |
| 405 | Method is unsupported. The response includes `Allow` when supplied by the router. |
| 409 | The operation conflicts with an existing identifier, relationship, active visit or queue state. |
| 410 | The walk-in QR code has expired or was revoked. |
| 413 | The Next.js proxy rejected a payload over its route limit. |
| 422 | A well-formed request failed schema or business validation. At most 25 field issues are returned. |
| 429 | A request limit was reached. Sign-in throttling returns `Retry-After`. |
| 500 or 503 | An unexpected server failure or temporary backend failure. Responses use generic messages. |
| 504 | A database statement or lock wait exceeded its configured limit, or Next.js ran out of time waiting for the API. |

The same error envelope is used by the legacy API and its same-origin proxies.
Legacy responses also retain `detail` as a message or a sanitized list for
existing clients. Error messages and validation details omit submitted values,
unknown field names, raw database diagnostics, and exception messages. A direct
caller can supply a single UUIDv4 in `X-Request-ID`. Next.js generates its own ID
and sends it to FastAPI. IDs correlate requests and carry no authorization.

## Local example

Set `QUEUESENSE_API` to the private local API URL and `QUEUESENSE_ORIGIN` to a configured browser origin. Supply credentials through a private JSON file with restricted permissions. Use a private cookie jar and remove it after logout.

```sh
curl -sS -c "$QUEUESENSE_COOKIE_JAR" \
  -H "Origin: $QUEUESENSE_ORIGIN" -H 'Content-Type: application/json' \
  --data-binary @"$QUEUESENSE_LOGIN_FILE" "$QUEUESENSE_API/api/v1/auth/login"

curl -sS -b "$QUEUESENSE_COOKIE_JAR" \
  "$QUEUESENSE_API/api/v1/queue?status=waiting&page_size=10"
```

[v1 API tests](../backend/tests/test_api_v1.py) · [Error and rollback tests](../backend/tests/test_api_reliability.py) · [Proxy regression test](../frontend/tests/api-errors.cjs)

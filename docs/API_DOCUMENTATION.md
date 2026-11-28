# QueueSense API documentation

| Interface | Intended client | How to explore |
| --- | --- | --- |
| Next.js same-origin clinic proxy | Staff and patient browsers | Run the local demo and use the web interface. The proxy forwards only approved routes. |
| FastAPI staff API under `/api/v1` | Authorized internal clients | Use the development Swagger UI at `http://127.0.0.1:8001/docs` or the [staff API reference](API_REFERENCE.md). |
| Partner weekly waiting-time API | Approved subscribed applications | Review the [OpenAPI file](../api-management/openapi.yaml) and [Postman collection](../api-management/queuesense.postman_collection.json). Hosted invocation and portal publication are pending. |

Clinic and partner credentials use different trust policies. See the [JWT and gateway security architecture](SECURITY_ARCHITECTURE.md) and [HTTP 429 handling](TRAFFIC_MANAGEMENT.md#http-429-and-retry-behavior).

## Partner API

The Developer Portal publication contract is [`api-management/openapi.yaml`](../api-management/openapi.yaml). It declares one read-only operation under the **Waiting time** tag. Import this file into Choreo. It contains the schemas, error and response examples, and the relative origin path. For a client, use the versioned invocation base copied from the Developer Portal. [Gateway design](../api-management/gateway-design.md)

| Method and resource | Request | Authorization |
| --- | --- | --- |
| `GET /wait-time-summary` | Required query parameters `department_id` (UUID) and `week_start` (ISO date for a Monday). The requested week must be completed in Asia/Colombo. | Choreo OAuth 2.0 access token from an approved application and subscription. QueueSense requires a valid gateway assertion for the approved proxy context and checks the department grant. |

Clients place the access token in `Authorization: Bearer <access token>`. Obtain it from the key manager shown for the application in the target environment. Use the client credentials grant for service clients. The bearer security declaration keeps the collection portable across environments. The access token is issued externally and the token URL is provided by the portal. Choreo forwards its own signed `X-JWT-Assertion` to the origin over mutual TLS. The origin's exact proxy-context and department checks are the authorization scope. No vendor-specific OAuth scope name is assumed. QueueSense staff JWTs and session cookies belong to the clinic API. [Credential and invocation workflow](DEVELOPER_PORTAL_GUIDE.md)

```sh
curl --silent --show-error --include --get \
  "${CHOREO_GATEWAY_URL%/}/wait-time-summary" \
  --header "Authorization: Bearer ${CHOREO_ACCESS_TOKEN}" \
  --header 'Accept: application/json' \
  --data-urlencode "department_id=${QUEUESENSE_DEPARTMENT_ID}" \
  --data-urlencode 'week_start=2026-11-02'
```

A successful response contains the requested department and week. For a cohort with at least ten measured waits, `metrics` contains the count, mean, median and 90th percentile in minutes.

```json
{
  "data": {
    "department_id": "5853b5a7-cfa4-4c3d-9c06-e97ce42487a1",
    "week_start": "2026-11-02",
    "suppressed": false,
    "metrics": {
      "measured_waits": 42,
      "average_wait": 14.2,
      "median_wait": 12.0,
      "p90_wait": 25.0
    }
  }
}
```

An empty or smaller cohort returns HTTP 200 with `suppressed: true` and `metrics: null`. The values above are synthetic. Use the actual approved department UUID for an invocation.

| HTTP status | QueueSense origin meaning |
| --- | --- |
| 400 | Malformed request. |
| 401 | Required gateway assertion is absent, invalid or expired. |
| 403 | Verified assertion has an unapproved proxy context, or the requested department is outside the grant. |
| 422 | Missing or invalid query values, an unsupported query field, or an incomplete clinic week. |
| 429 | Origin quota reached. The JSON error code is `rate_limited`. Read the integer `Retry-After` header and wait before retrying. |
| 500 | Unexpected application error. |
| 503 | Signing keys or the database are temporarily unavailable. |
| 504 | Database operation timed out. |

Origin errors contain `success: false`, `error` with a stable `code` and `message`, and a `request_id`. The origin returns `X-Request-ID` and `Cache-Control: no-store`. A gateway-generated authentication, quota or availability error may use a different envelope or headers. [Retry and traffic behavior](TRAFFIC_MANAGEMENT.md)

## Clinic-facing HTTP endpoints

The clinic browser uses the same-origin Next.js proxy with cookies for staff and private capability links for patients. Routes below use their FastAPI paths. They are outside the partner publication contract. State changes require a configured `Origin`, including clinic sign-in and recovery. Private link keys are bearer capabilities in the path. Do not log them or use them as patient registry identifiers. [Role and permission matrix](ROLE_PERMISSION_MATRIX.md)

### Unauthenticated entry points and credential exchange

| Method and path | Request | Success response |
| --- | --- | --- |
| `GET /health` | No body or credentials. Used at private service ingress. | 200 `{status: "ok"}` when the runtime database check succeeds. |
| `GET /health/live` | Private infrastructure probe. | 200 with `status: "ok"` when the API process handles the request. |
| `POST /auth/login` | JSON `email`, `password`, `role`, optional `otp`. | Staff identity and expiry with HttpOnly session cookies. |
| `POST /api/v1/auth/login` | Same credentials and Origin requirement. | `data` staff identity. JWT mode also returns `access_token` and `token_type: "Bearer"`. The refresh credential is delivered as an HttpOnly cookie. |
| `POST /auth/refresh`, `POST /api/v1/auth/refresh` | Current refresh cookie in JWT mode. Development opaque mode uses the session cookie. | Replacement cookies and identity. The v1 JWT response includes the new access token. |
| `POST /auth/logout`, `POST /api/v1/auth/logout` | Caller session credentials if present. The v1 route also accepts an access bearer token in JWT mode. | Browser acknowledgement or v1 HTTP 204. |
| `GET /auth/demo`, `POST /auth/demo` | GET requires no body. POST requires a demo `role` and an allowed Origin. | GET returns the enabled flag. POST issues a demo staff session when enabled and returns 404 otherwise. |
| `POST /auth/recovery/request` | JSON `email`. | Generic acknowledgement message. The response does not identify whether an account exists. |
| `POST /auth/recovery/reset` | JSON recovery `token`, new `password`, optional `otp`. | Success acknowledgement after password reset. |

Exact staff token requirements, rotation behavior and private REST schemas are in the [JWT guide](JWT_AUTHENTICATION.md) and [Staff API reference](API_REFERENCE.md). The [staff analytics preview](../api-management/staff-preview.openapi.yaml) uses the existing staff token and is intended for private origin testing. Interactive origin documentation is a development feature.

### Patient, appointment and kiosk links

| Method and path | Request | Success response |
| --- | --- | --- |
| `GET /patient/{key}` | A private queue tracking key. | Token label, department, state, priority class, staff-safe wait estimates and completed wait information when available. Unavailable estimates are JSON null. |
| `GET /patient/{key}/qr` | Queue key and configured clinic URL in query parameter `origin`. | SVG QR code for this tracking link. |
| `GET /patient/{key}/events` | Queue key. | `text/event-stream` with `ready` and `change` events and an empty payload. Fetch the status resource after a change event. |
| `GET /patient/{key}/doctors` | Queue key. | `doctors` entries with `name`, `availability`, `expected_wait`, and a `notice`. |
| `GET /patient/{key}/feedback` | Queue key. | `eligible` and `submitted` flags. |
| `POST /patient/{key}/feedback` | Queue key and JSON `rating` integer 1–5, optional `comment` up to 1,000 characters. | HTTP 201 with `submitted: true` for a completed visit. |
| `GET /patient/{key}/notifications` | Queue key. | List of notifications with `id`, `kind`, `message`, `created_at`, and `is_read`. |
| `POST /patient/{key}/notifications/{notification_id}/read` | Queue key and notification UUID. | `{ok: true}` for a notification owned by this visit. |
| `GET /self-checkin/{key}` | Private appointment or kiosk key. | `kind`, `department`, nullable `reference` and `starts_at`, `status` and `active`. |
| `POST /self-checkin/{key}` | Appointment or kiosk key and JSON `request_id` UUID. | `patient_key` for the resulting queue visit. Reuse the request ID after a kiosk retry. |
| `GET /self-checkin/{key}/qr` | Appointment or kiosk key and configured clinic URL in `origin`. | SVG QR code for this arrival link. |
| `GET /self-checkin/{key}/notifications` | Appointment key. | `confirmed_at`, `status`, `attendance_outcome` and ordered `notifications`. |
| `POST /self-checkin/{key}/confirm` | Appointment key. | `{ok: true}` for an open booking. |
| `POST /self-checkin/{key}/notifications/{notification_id}/read` | Appointment key and notification UUID. | `{ok: true}` for a notification owned by this booking. |

Each delivery operation below exists under both `/patient/{key}/delivery` and `/self-checkin/{key}/delivery`. The latter requires an appointment link.

| Method and operation suffix | Request | Success response |
| --- | --- | --- |
| `GET` base | Private link. | `capabilities` and `targets` with masked destination and verification state. |
| `POST` base | JSON `channel` (email or sms), `destination`, and `consent: true`. | `ok` and a message after the verification code is sent. |
| `POST /{channel}/verify` | Channel and JSON six-character `code`. | `{ok: true}` after verification. |
| `POST /{channel}/disable` | Channel. | `{ok: true}` after removing the destination. |
| `POST /push` | JSON HTTPS `endpoint`, `keys` with `auth` and `p256dh`, and `consent: true`. | `{ok: true}` after registering the subscription. |

The browser surface adds the legacy `detail` field to safe errors. Invalid or mismatched links return 404. Revoked or expired kiosk URLs return 410. Ineligible booking and feedback operations can return 409. Provider failures can return 503. Public and capability budgets may return 429. [Origin rate limits](TRAFFIC_MANAGEMENT.md)

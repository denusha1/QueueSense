# QueueSense security implementation

## Request path

1. A browser uses the same-origin Next.js routes. For a mutation, Next.js compares the canonical Origin with the request host and `FRONTEND_ORIGINS`. It forwards only routed requests and selected session cookies to the configured FastAPI origin.
2. FastAPI independently requires one approved Origin header on mutations. Its authenticated staff dependencies verify the request credential and query the active account, session and grants. JWT clients use the configured staff issuer, audience and signature. A patient URL instead authorizes access to its specific object.
3. Services enforce named permissions and apply resource limits in SQL. Doctor lists, counts, details and history use the active staff profile tied to the account. An inaccessible visit returns the same `404` as an absent visit. [Role and ownership rules](ROLE_PERMISSION_MATRIX.md)
4. Browser-facing API responses suppress caching and referrers. The proxy accepts JSON, generated SVG QR codes, reports, or event streams according to the route. Invalid upstream media becomes a generic error, and event streams carry `Cache-Control: no-store, no-transform`.
5. An error response contains a correlation ID, a stable code and a safe message. Logs identify the event, endpoint pattern and exception type. Patient links and credential headers need redaction in hosting and gateway logs as well. [API errors](API_REFERENCE.md#error-contract)

## Deployment configuration

Apply PostgreSQL migrations through `017_staff_authorization.sql` and use the restricted runtime role. It needs read access to `roles`, `permissions` and `role_permissions`. Use `APP_ENV=production` with demo sign-in disabled, configure exact HTTPS values in `FRONTEND_ORIGINS`, and supply `JWT_SIGNING_SECRET` and provider credentials through the deployment secret manager. Serve browser traffic over TLS and apply HSTS at the public TLS ingress. Keep PostgreSQL and the FastAPI origin private. [JWT secret configuration](JWT_AUTHENTICATION.md) · [Deployment](DEPLOYMENT.md)

The current browser contract requires no CORS allowlist. To publish an integration browser API later, define its own origins and credential model before adding CORS. Keep the Next.js browser proxy constrained to the QueueSense origin. Native API integrations and contract tests should send an allowed Origin for mutations under the current API contract. [API reference](API_REFERENCE.md)

| Existing control | Scope |
| --- | --- |
| Sign-in rate limits | PostgreSQL rolling window of 15 minutes. Five failed attempts per account or sixty attempts per backend peer reach the limit. |
| Account recovery and MFA budgets | Existing database-backed limits return `429` with a 15-minute retry hint. |
| Walk-in kiosks | Twenty new arrivals per kiosk per minute. Successful request-ID replays return the original receipt. |
| Patient queue status | Six hundred requests per process per minute. A locked window supplies `Retry-After`. |
| Browser body limits | 4 KB for auth requests and 2.1 MB at the service proxy. Import continues to validate its independent CSV size and row limits. |

## Verification

```sh
.venv/bin/python -m backend.verify_local
npm --prefix database test
npm --prefix frontend run build
node frontend/tests/api-errors.cjs
node frontend/tests/jwt-session.cjs
npm --prefix frontend audit
npm --prefix database audit
pip-audit --no-deps -r backend/requirements.lock
```

The browser tests expect the local synthetic app to be running. JWT browser tests require a locally configured JWT signing secret. Backend coverage includes staff role denial and grant revocation, attempts to use another patient’s notification, spoofed JWT role claims, an unexpected signing header, invalid Origins, disabled cross-origin preflights, validation redaction, literal SQL search, and concurrent request limits. Existing JWT tests cover bad signatures, expiry, malformed credentials and session revocation. [Authorization tests](../backend/tests/test_authorization.py) · [Hardening tests](../backend/tests/test_security_hardening.py) · [JWT tests](../backend/tests/test_jwt_auth.py)

Release owners still need to verify TLS and log redaction at ingress, run the release advisory scans, test real outbound providers with approved destinations, and verify Choreo JWT and quota policies before enabling external traffic. [Residual risks and review evidence](SECURITY_AUDIT.md#remaining-risks)

# QueueSense staff JWT authentication

QueueSense issues staff access JWTs after the existing email, password, role, and MFA checks. Passwords use Argon2id. The existing PostgreSQL login attempt limits remain in place. Every staff request still looks up the current user, role, and active session in PostgreSQL, so role changes and revocation take effect on the next protected request.

## FastAPI token policy

| Setting | Default | Rule |
| --- | --- | --- |
| `JWT_SIGNING_SECRET` | Required in production | Supply at least 32 random bytes encoded as URL-safe Base64 through the deployment secret manager. Use the same key across replicas in one environment and a separate key in each environment. |
| `JWT_ISSUER` | `queuesense-staff` | Must match the configured issuer exactly. Use an environment-specific value for deployed installations. |
| `JWT_AUDIENCE` | `queuesense-private-api` | Must be a single string that exactly matches the configured audience. |
| Signing algorithm | `HS256` | FastAPI fixes the allowlist to HS256 and verifies the signature with PyJWT. [PyJWT validation reference](https://pyjwt.readthedocs.io/en/stable/api.html) |
| `JWT_ACCESS_TTL_SECONDS` | 600 seconds | Accepted range is 60 to 900 seconds. Access expiry is capped at the session's absolute expiry. |
| `JWT_REFRESH_TTL_SECONDS` | 28,800 seconds | Accepted range is 300 to 86,400 seconds and must exceed the access TTL. Refresh rotates the credential without extending that absolute lifetime. |

The access JWT uses `typ=at+jwt` and `token_use=access`. The validator requires `iss`, `aud`, `sub`, `sid`, `jti`, `iat`, `nbf`, and `exp`. It enforces canonical UUIDs for subject, session and token ID, integer timestamps, configured lifetime, and zero expiry leeway. After verification, FastAPI checks that `sid` belongs to `sub`, that the session is active and unexpired, and that the user's account is active. Roles, contact data and patient data are excluded from JWT claims. Invalid or missing credentials receive a generic 401 with a request ID.

## Browser, v1 clients, and revocation

- The Next.js login, demo and renewal routes use HttpOnly cookies. Production uses Secure cookies. The access cookie uses SameSite=Lax and refresh uses SameSite=Strict. Both cookies are host-only so Next.js and the private FastAPI instance can serve the same browser origin; the proxy forwards the refresh cookie only for sign-in, refresh and logout. Browser JavaScript receives identity and expiry metadata and keeps credentials out of browser storage.
- Private v1 routes accept the access cookie or an `Authorization: Bearer <access JWT>` header when JWT is enabled. The private v1 login and refresh JSON responses include `access_token` and `token_type`. The refresh credential is available only via `Set-Cookie`; keep the cookie jar private. Existing write Origin checks also apply to these operations. [Endpoint reference](API_REFERENCE.md)
- Each session stores the SHA-256 digest of its current random refresh credential. Refresh atomically replaces that digest and returns a new access JWT. One submitted refresh credential can succeed once. A consumed credential fails without revoking the replacement session. An earlier access JWT remains usable until its short expiry while the associated session is active.
- Logout, account password changes, role changes and session revocation invalidate the underlying session, which blocks both access and refresh. Logout clears both browser cookies. A valid bearer access JWT can revoke its own session with the v1 logout route.
- The workspace attempts renewal before access expiry and when a browser reload has only the refresh cookie. Where supported, browser Web Locks coordinate tab refreshes. An expired or revoked refresh session returns the browser to sign-in.
- The public endpoints consist of minimal health, sign-in and recovery entry points, and patient/arrival flows gated by their own capability links. Demo issuance is disabled and interactive API docs are hidden in production. Staff pages, service health, queue streams, and staff operations require authenticated access. Private patient links operate independently of staff credentials.

## Migration and operating the signing key

Apply forward migration 016 before deploying the API. It labels existing sessions as opaque and preserves their rows. In a non-production environment, omitting the secret retains the previous opaque session mode for compatibility. Setting the secret enables JWT mode and requires old opaque sessions to sign in again. Production requires the secret at startup.

Generate a random deployment key with a secret manager or `secrets.token_urlsafe(32)` in a private provisioning process. When rotating, replace the key across replicas as one deployment so access tokens signed under the old key become invalid. Unexpired refresh sessions can then obtain access JWTs under the replacement key. During a compromise, revoke affected staff sessions as well. Use TLS for the browser and private API ingress, and redact cookies and Authorization headers from proxy and infrastructure logs.

## Choreo API Gateway trust

FastAPI issues and validates the QueueSense staff JWT described above. Keep the symmetric staff key in QueueSense. The planned Choreo managed integration has a separate OAuth issuer, audience, consumer credentials and publication scope. Configure the gateway to validate integration consumer credentials under that trust policy. Where the gateway sends a signed backend JWT in `X-JWT-Assertion`, the integration origin must verify that assertion with the gateway's public keys and a dedicated integration audience. QueueSense staff routes accept the QueueSense staff issuer and audience. This stage verified the staff flow locally. Gateway configuration and verification belong to the integration rollout. [Official Choreo gateway assertion and JWKS guide](https://choreolabs.com/engineering-platform/developer-platform/docs/developer/authentication-and-authorization/pass-end-user-attributes-to-upstream-services/)

## Verification

Run `.venv/bin/python -m backend.verify_local` for validation and revocation tests. Start the synthetic demo with JWT enabled and run `node frontend/tests/jwt-session.cjs` to verify HttpOnly cookies, workspace renewal and logout through Next.js.

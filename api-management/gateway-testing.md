# QueueSense Gateway verification

## Local checks

Run from the QueueSense repository root. See the Stage 10 [tooling setup](choreo-integration-plan.md#repository-work-completed) for the OpenAPI validation dependencies.

```sh
.venv/bin/python -m backend.verify_local
PYTHONPATH=. python api-management/generate_openapi.py --gateway --check
python -m openapi_spec_validator api-management/openapi.yaml
```

The origin tests use PostgreSQL and synthetic signing keys. They cover disabled configuration, missing and duplicate assertions, wrong signature, issuer, audience or proxy context, expired assertions, forbidden departments, invalid query windows, JWKS unavailability, small-cohort suppression and the read-only aggregate response. These checks do not start a Choreo deployment.

Verification on 26 November 2026 passed all 142 backend tests and validated both OpenAPI files. A local container exercise used the repository Nginx configuration, FastAPI and PostgreSQL, and a synthetic HTTPS JWKS server. It verified private health, TLS client certificate enforcement, signed assertion forwarding, the 404 path and 405 method boundaries, a successful response with correlation and no-store headers, and recovery after an upstream outage returned 504.

## Development verification after the owner configures Choreo

1. From the private runtime network call `GET /health` on FastAPI port 8001. Record `200` and `{"status":"ok"}`. From the ingress, verify private name resolution and access to that port. Keep /health out of the HTTPS integration endpoint.
2. In Choreo select **Test → OpenAPI Console → Development** and invoke the single GET operation with the approved department and a past Monday. Verify that the origin saw the target base and resource appended exactly once. Then test with an approved application OAuth credential against the actual invocation URL. Record status, request ID if present, and the response shape. [Official test procedure](https://wso2.com/engineering-platform/developer-platform/docs/tutorials/expose-a-service-as-a-managed-api/)
3. Run the matrix below against synthetic fixtures. For upstream failures, use only a disposable Development origin. Preserve evidence without logging tokens, assertions, client secrets or patient data.

| Request or condition | Verify |
| --- | --- |
| Approved OAuth application, correct mTLS, valid gateway assertion, approved department and past week | HTTP 200 JSON, documented aggregates or suppression, correlation headers as observed, no patient fields or cookies. |
| Missing or invalid client OAuth credential, or an application outside the approved access policy | Gateway denies the request. Verify an unapproved application cannot reach the origin operation. |
| A client-supplied assertion header | Verify the caller cannot substitute its own assertion for the gateway-issued assertion. The origin rejects multiple assertion headers. |
| Another proxy context, wrong issuer/audience, or another department | Origin denies. Authenticated wrong contexts and departments return 403. Invalid assertions return 401 at the origin. |
| GET to the origin without the approved Choreo client certificate | TLS/ingress denies access. The request never reaches FastAPI. |
| POST, HEAD, arbitrary paths, /health or the staff API on the integration HTTPS host | Ingress or gateway denies the request. Verify corresponding requests never reach the private staff routes. |
| Invalid UUID, unknown query fields, or a week still in progress | Origin returns its sanitized 422 JSON where the request passes gateway validation. |
| Unreachable private upstream or database outage | Observe the origin, ingress and gateway errors separately. Verify a resulting non-2xx and recovery after restoration, with no credentials or diagnostics in client responses. |
| Choreo signing key rotation or temporary trusted JWKS outage | Verify normal rotation and a controlled denial during unavailable or untrusted key material. |
| Request limit reached after quotas are configured | Verify actual gateway throttling status, headers and recovery. |

Record the real Development Service address, HTTPS Target, gateway URL, deployment revision and observed statuses. Live gateway-to-origin connectivity, credentialed invocation and Choreo deployment remain pending owner configuration.

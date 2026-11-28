# QueueSense release checklist

Use this checklist for each approved environment. Complete hosted items with evidence from that environment.

## Preparation

- [ ] Record release commit, image digests, environment, operator and rollback owner.
- [ ] Confirm GitHub-hosted backend, frontend and deployment preparation workflows passed.
- [ ] Approve separate Development and Production secret sets and access roles.
- [ ] Confirm database backups and complete a restore drill.
- [ ] Apply all numbered migrations with the owner identity. Confirm least-privilege runtime grants and model registration.
- [ ] Verify database connection limits for the expected pool size, replicas and SSE listeners.

## Development verification

- [ ] Confirm both deployed containers are healthy with real service addresses and approved certificates.
- [ ] Verify Next.js reaches the private API. Confirm valid staff JWT acceptance, invalid token rejection, role boundaries and refresh/logout.
- [ ] Register a synthetic patient, issue a token, track it and complete it as the assigned doctor.
- [ ] Confirm HTTP 429 and retry behavior for the application and the hosted gateway separately.
- [ ] In disposable infrastructure, verify readiness failure, independent liveness, proxy errors and recovery from both database and API outages.
- [ ] Verify the approved partner client reaches the single gateway operation over HTTPS with OAuth, mTLS and a trusted signed assertion at the origin.
- [ ] Verify forbidden paths, invalid assertions, unauthorized departments, inaccessible private health/metrics and the subset of gateway responses documented in OpenAPI.
- [ ] Confirm Choreo Service health and logs, gateway Insights, private scraper access and alert delivery.
- [ ] With owner approval, verify the intended Developer Portal visibility and subscription using a test application and environment-specific credentials.

## Production acceptance

- [ ] Obtain explicit promotion and publication approval from the environment owner.
- [ ] Record the actual deployed revisions, service and gateway addresses, DNS/TLS evidence, migration versions and selected policy limits.
- [ ] Verify health and run the approved non-destructive checks against the deployed release. Use synthetic fixtures only in an approved staging or fixture environment.
- [ ] Confirm monitoring and rollback readiness. Record the decision, measurements and unresolved items.

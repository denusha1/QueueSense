# QueueSense technical interview guide

## Opening explanation

“QueueSense connects clinic check-in, queue updates, and private patient tracking. I can walk through how the application preserves token uniqueness under concurrency, uses PostgreSQL for session revocation and rate limits, and prepares a small partner API for Choreo. I can show local tests of the origin and be precise about the hosted work still required.”

## Topics and project examples

| Topic | Explain it using QueueSense |
| --- | --- |
| API gateway and API proxy | A proxy represents an upstream API and forwards allowed requests. A gateway is the runtime entry point that handles cross-cutting policies such as authentication, quotas and routing. QueueSense prepares one Choreo API Proxy with one GET operation. The gateway would enforce consumer credentials and subscriptions, and the origin would verify the forwarded assertion. |
| Gateway and service mesh | A gateway commonly manages traffic entering a system from consumers. A service mesh provides service identity, traffic policy and telemetry between workloads. QueueSense keeps closely coupled workflows in one API process, so its documented architecture uses a gateway boundary for partner traffic without a service mesh. |
| REST design | Model patients, tokens and doctors as resources. Use GET for reads, POST for creation and PATCH for state changes. Return 201 with a resource location on creation, 409 for a duplicate active token, and paginated results for collections. |
| JWT | A JWT carries claims. FastAPI fixes HS256 for staff, checks the issuer, audience and lifetime, and consults PostgreSQL for active-session and role state. A signed token's claims are readable. The partner origin separately checks an RS256 Choreo assertion. |
| OAuth 2.0 | OAuth defines how a client gets access to protected resources. In the proposed machine-to-machine flow, the subscribed client uses client credentials to obtain an access token. JWT describes a token format. An OAuth token can have a different format. |
| RBAC | Roles group permissions. Check each operation at FastAPI, then check ownership for resources such as a doctor’s assigned visit. A patient capability gives access to its own linked resource. |
| Rate limiting | Use a fixed database-clock window keyed to the relevant account, link or partner department. The atomic update works across workers. A limited request returns 429 and Retry-After. Gateway quotas add a separate layer after hosted setup. |
| OpenAPI | A machine-readable contract documents HTTP paths, schemas, security requirements and examples. The partner contract exposes one operation. CI validates it and compares generated artifacts to catch drift. |
| API lifecycle | Verify the draft in an approved environment. Review visibility, publish, subscribe an application, and smoke-test with a real approved credential. Version, deprecate and retire through the documented lifecycle as consumers migrate. |
| Docker | Separate migration from app startup. Connect services over private Compose networks, run app containers as non-root, keep a persistent PostgreSQL volume and inject secrets at runtime. |
| CI/CD | Pull requests fan out to backend, frontend and deployment-preparation checks. Build and test reports are captured as artifacts. The separate manually dispatched Choreo workflow targets Development only. |
| Load testing | Locust exercised mixed traffic at 10, 50 and 100 users with wait time between operations. Explain throughput, error rate and tail latency separately. At 100 users the aggregate p95 fell, while token issuance p99 rose. |
| Monitoring | Use request IDs for incident correlation, counters for errors and 429s, and histogram buckets for p95. Liveness checks the process. Readiness checks PostgreSQL access. Gateway Insights and application metrics describe different traffic boundaries. |

Primary references for the underlying concepts and platform workflow. [JWT](https://www.rfc-editor.org/info/rfc7519/) · [OAuth 2.0](https://www.rfc-editor.org/info/rfc6749/) · [Service mesh](https://istio.io/latest/docs/overview/what-is-istio/) · [Choreo API Proxy](https://wso2.com/engineering-platform/developer-platform/docs/develop-components/develop-proxy/develop-an-api-proxy-from-an-open-api-specification/)

## Follow-up questions to rehearse

- **How did you prove concurrency correctness?** Describe the session lock, the partial unique index, atomic conflict handling, rollback, and the two-request test.
- **Why a modular monolith?** Queue issuance and arrivals share transactions. Splitting reporting or delivery could make sense if operational evidence shows a different scaling or ownership boundary.
- **What happened when PostgreSQL was down?** Readiness returned a correlated 503 while liveness stayed healthy. The Compose smoke restored the database and checked the same patient visit again.
- **What evidence can you show for Choreo?** Show the OpenAPI and Postman files, ingress configuration, and the local HTTPS/mTLS exercise. Explain the required hosted organization, OAuth subscription and portal acceptance steps. [Testing report](TESTING_REPORT.md) · [Contribution report](CHOREO_INTERNSHIP_CONTRIBUTION_REPORT.md)

# QueueSense enterprise implementation roadmap

Stage 1 records the existing application and its evidence. Stages 2–20 are the audit's proposed sequence. Complete and verify each stage independently, and use the user's later stage prompts to confirm its exact scope. See the [audit](PROJECT_AUDIT.md), [architecture and API inventory](EXISTING_ARCHITECTURE.md), and [technical debt register](TECHNICAL_DEBT.md).

## Stage 2 — Establish backend module boundaries

Make a small, behavior-preserving change to FastAPI's structure. Today feature modules import settings, database and authentication helpers from the entry point that wires those same modules together. Moving stable dependencies out of that entry point will let later stages add a versioned API and JWT checks without weaving them into staff cookie handlers.

1. Capture the existing method/path set and characterize response status, body, cookies and headers for health, sign-in and a protected workspace route. Record the baseline count of 98 operations.
2. Extract typed configuration and the PostgreSQL connection helper from [backend/app.py](../backend/app.py) into small modules. Preserve the app factory and the import compatibility that existing tooling and tests rely on. Keep commit and rollback behavior intact.
3. Put one low-risk slice, such as `GET /health`, behind an explicit FastAPI router. Keep the same URL, status, response and database-backed semantics. Leave browser routes, queue logic, session revocation and database migrations intact.
4. Run the native backend verifier and compare the generated method/path set with the baseline. Cover cookie/origin behavior and relevant API contracts with focused regression checks where existing tests leave a gap. Update backend architecture notes with the new ownership boundaries.

**Exit conditions.** The existing app factory continues to launch. Health and representative auth/queue tests pass. Existing routes, browser proxy paths, migrations and external behavior are preserved. The refactoring leaves a clear place for a later integration API. JWT, managed gateway configuration and portal publishing belong to subsequent stages.

## Stage sequence and acceptance evidence

| Stage | Work | Evidence to close the stage |
| --- | --- | --- |
| 1. Existing project audit | Establish the repository baseline and record concrete risks and preservation requirements. | Four audit documents and fresh local check results. |
| 2. Backend foundations | Separate configuration and connection ownership. Move a small compatible router slice. | Existing route inventory and behavior verified against native tests. |
| 3. REST API contract | Define versioned integration routes, data exposure, response and error shapes, pagination, and compatibility rules. Start with a restricted read-only pilot using shared business logic. | Contract tests and consumer examples with synthetic fixtures. Browser regression tests pass. |
| 4. JWT authentication | Choose the trust model and issuer from confirmed integration requirements. Verify signature, issuer, audience, validity windows, and signing-key rotation. Keep the browser's revocable cookie flow compatible. | Tests with local signing fixtures for valid, invalid, expired and rotated credentials. |
| 5. Authorization | Define staff role and integration client scope/field matrices. Apply least privilege and preserve doctor ownership constraints. | Test each allowed and denied route class and exclude staff/admin/private capability routes from the integration surface. |
| 6. API security | Fix capability-path logs, validate production configuration, align request bounds and document data retention. Address recovery timing if applicable to the deployed installation. | Negative tests for logs, errors, origins, configuration and unauthorized requests. |
| 7. Rate limiting | Specify per-operation limits and client identity across replicas. Align app and future edge behavior, including retry headers and SSE policy. | Multi-worker quota and recovery tests with synthetic clients. |
| 8. OpenAPI and API documentation | Build a curated integration OpenAPI artifact, error examples, auth scopes, compatibility notes and onboarding instructions. | Schema lint, parity checks and synthetic request/response examples. |
| 9. Container deployment | Reproduce API/frontend/database builds and startup. Add health checks, restricted database grants and environment handoff. Verify lifecycle and migrations in containers. | Full local Compose smoke from a fresh database, including restart and data persistence. |
| 10. CI validation | Use deterministic installs and broaden test execution. Add container and contract checks, then define required checks. | Hosted workflow results for a concrete revision. |
| 11. Automated regression suite | Extend backend, proxy and browser tests for full queue lifecycle, SSE reconnect, account/privacy paths, paging, schedule races and upgrade data. | Repeatable tests against isolated synthetic fixtures and documented failure modes. |
| 12. Observability | Define liveness, readiness, metrics, traces and alerting for API, database, streams, automation and model fallback. | Dashboards and alerts exercised with synthetic traffic and validated redaction. |
| 13. Load and resilience | Test mixed check-in, live SSE, status, analytics and exports. Measure tail latency, lock waits, connections, error rates and delivery backlogs. | Reproducible workload and results tied to a named environment. Prioritize optimizations measured against that baseline. |
| 14. Choreo discovery | Confirm organization access, environments, connectivity, approved exposure and supported API import, auth, gateway/proxy and portal workflows against current official documentation. | Document product choices with verified official references and assigned external owners. |
| 15. Staging origin deployment | Provision private API/database and frontend connectivity. Configure secrets, TLS, migrations, backup and test data. | Staging smoke, database restore rehearsal and verified access boundaries. |
| 16. Managed API and gateway | Configure the approved integration operations only. Apply the verified gateway auth/traffic policy and evaluate a managed proxy if the selected workflow calls for one. | Gateway requests prove allow/deny behavior, rate limits, proper error handling and blocked access to internal routes. |
| 17. Developer Portal and subscription | Publish the curated contract with synthetic examples and subscribe using a test consumer. | Portal visibility and an end-to-end subscribed request verified in the intended environment. |
| 18. Release pipeline | Establish build promotion, migrations, environment approvals and rollback across staging and production. | A staging promotion and rollback rehearsal tied to immutable artifacts. |
| 19. Production readiness and deployment | Review quotas, ownership, privacy, backup and incident response. Release through the approved environment and validate the managed API and existing clinic flows. | Verified rollout, smoke results, alerts, recovery checks and rollback readiness. |
| 20. Handoff and documentation | Publish architecture, operations, API onboarding, incident and backup runbooks. Reconcile verification claims and outstanding work. | Maintainer handoff with ownership, evidence, revision references and unresolved steps. |

## Decisions and external prerequisites

| Item | Current decision or pending evidence |
| --- | --- |
| Compatibility | Preserve the current Next.js browser proxy, cookie session and patient capabilities. Build the integration contract on explicit approved routes and shared business logic. |
| Data | Use synthetic fixtures in CI, load and gateway onboarding. Define retention/access rules, model validation and ownership before taking real clinic traffic. No multi-tenant design is assumed. |
| Choreo and identity | Pending organization/project access, issuer choice, origin reachability, verified product workflow, API visibility and a test consumer. The roadmap prescribes a verification step for current official documentation and supplies no product-specific configuration or commands. |
| Infrastructure | Pending staging/production hosting access, private networking, DNS/TLS, deployment/secret configuration, backup targets, and operational owners. |
| Release evidence | Record tested revision and environment, commands, test results, configuration decisions and unresolved manual steps in each stage. Deployment and portal subscription close only after direct verification. |

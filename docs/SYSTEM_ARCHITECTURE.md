# QueueSense Enterprise system architecture

QueueSense runs a Next.js web server, a modular FastAPI monolith and PostgreSQL. The clinic path and the partner integration have separate entry points. The clinic stack and the dedicated HTTPS partner ingress have been exercised locally. The Choreo-managed portion requires hosted configuration. [Staging evidence](END_TO_END_TEST_REPORT.md)

## System overview

```mermaid
flowchart LR
    Browser["Clinic staff or patient browser"] --> Web["Next.js UI and same-origin proxy"]
    Web --> Staff["FastAPI clinic endpoints"]
    Client["Approved partner app"] -.-> Gateway["Choreo API Proxy · hosted setup pending"]
    Portal["Choreo Developer Portal · publication pending"] -.-> Client
    Gateway -.->|"mTLS and signed assertion"| Ingress["Nginx dedicated HTTPS ingress"]
    Ingress --> Partner["FastAPI integration endpoint"]
    subgraph Application["FastAPI process"]
        Staff --> Domain["Identity, queue, arrivals, analytics"]
        Partner --> Aggregate["Department-scoped aggregate"]
        Domain --> Prediction["Versioned prediction model"]
        Worker["Optional automation and delivery worker"]
    end
    Domain --> DB[("PostgreSQL")]
    Aggregate --> DB
    Worker --> DB
    Domain --> Telemetry["JSON logs, private metrics and health"]
    DB -.->|"LISTEN / NOTIFY on commit"| Domain
    Domain -.->|"SSE change signal"| Web
```

| Boundary | Responsibility and source |
| --- | --- |
| Next.js | Role workspaces, private tracking and a same-origin allowlist that forwards clinic auth, JSON, reports, images and SSE. [Proxy source](../frontend/services/api-proxy.ts) |
| FastAPI adapters | Browser-compatible routes, versioned staff endpoints and the conditional partner operation. Schemas validate inputs and constrain outputs. [App factory](../backend/app.py) · [v1 routes](../backend/api/v1) |
| Application modules | Identity, clinic operations, scheduling and arrivals, reports, inference, and optional delivery. [Services](../backend/services) · [Arrivals](../backend/arrivals.py) · [Automation](../backend/automation.py) |
| Data access | Psycopg transactions and parameterized SQL. Optional request pool for short database work. SSE retains dedicated listener connections. [Database runtime](../backend/database.py) · [Repositories](../backend/repositories) |
| PostgreSQL | Staff sessions and grants, clinic records, events, audits, reporting history and shared request budgets. [ER diagram](DATABASE_DESIGN.md#entity-relationships) |
| Operations | Health checks, per-worker metrics and scoped JSON logs. [Monitoring architecture](OBSERVABILITY_ARCHITECTURE.md) |

## Partner gateway request flow

```mermaid
sequenceDiagram
    participant C as Approved application
    participant OAuth as Hosted key manager
    participant G as Choreo API Proxy
    participant N as Dedicated HTTPS ingress
    participant A as FastAPI partner route
    participant P as PostgreSQL
    Note over C,G: Hosted OAuth, subscription and gateway checks pending
    C->>OAuth: Request token using client credentials
    OAuth-->>C: OAuth access token
    C->>G: GET wait-time-summary with bearer token
    G->>G: Enforce subscription, token and gateway policy
    G->>N: Send approved operation and signed assertion over mTLS
    Note over N,P: Origin path exercised locally with synthetic gateway credentials
    N->>A: Forward GET and X-JWT-Assertion
    A->>A: Verify JWKS signature, issuer, audience and proxy context
    A->>P: Apply department quota and read completed-week aggregate
    P-->>A: Counts and wait metrics
    A-->>N: Aggregate or suppressed result
    N-->>G: Return status, JSON and correlation header
    G-->>C: Return partner API response
```

The proxy exposes `GET /wait-time-summary`. The HTTPS Target supplies the base path `/api/integrations/v1`. The ingress forwards the allowed operation and drops consumer cookies and Authorization. FastAPI verifies the gateway assertion and enforces the configured department. The application enforces its own 30-read-per-minute quota and suppresses cohorts with fewer than ten measured waits. [Gateway and ingress configuration](../api-management/proxy-configuration.md) · [Partner contract](../api-management/openapi.yaml)

## Queue transaction and live updates

```mermaid
sequenceDiagram
    participant B as Reception browser
    participant W as Next.js
    participant F as FastAPI queue service
    participant D as PostgreSQL
    participant T as Connected trackers
    B->>W: Submit check-in with staff session
    W->>F: Forward allowlisted request
    F->>D: Resolve active session and permissions
    F->>D: Lock queue session and allocate next token
    F->>D: Write token, event and audit record
    alt Commit succeeds
        D-->>F: Commit
        F-->>W: Created token and private receipt
        W-->>B: 201 Created
        D-->>F: Notify listeners after commit
        F-->>T: Signal change so clients reload current state
    else Transaction fails
        F->>D: Roll back
        F-->>W: Safe failure and request ID
        W-->>B: Return failure status
    end
```

A modular monolith keeps transactions and deployment straightforward. Reporting, inference and notifications share runtime resources. Benchmark those workloads before introducing separate services. Read replicas, precomputed aggregates or a dedicated worker become useful when measured contention, independent scaling or separate ownership warrants them. [Decision records](TECHNICAL_DECISIONS.md) · [Deployment and CI diagrams](DEPLOYMENT_GUIDE.md)

# Role and permission matrix

QueueSense has four staff roles and a patient access role. An administrator can assign the staff roles `admin` (ADMIN), `reception` (RECEPTIONIST), `doctor` (DOCTOR), and `manager` (MANAGER). The PATIENT role uses the private link for a single queue visit or appointment. A patient can use that link without a staff account.

## Staff permissions

| Capability | PostgreSQL permissions | ADMIN | RECEPTIONIST | DOCTOR | MANAGER |
| --- | --- | --- | --- | --- | --- |
| Own profile, password, sessions and notification destinations | `account:self` | Yes | Yes | Yes | Yes |
| Administrator MFA and staff recovery | `account:security` | Yes | — | — | — |
| Staff account administration | `users:manage` | Yes | — | — | — |
| Department directory | `department:read` | Yes | Yes | Yes | Yes |
| Department management | `department:manage` | Yes | — | — | — |
| Clinician directory and schedules | `doctor:read` | Yes | Yes | Yes | Yes |
| Clinicians, schedules and service profiles | `doctor:manage` | Yes | — | — | — |
| Live queues, queue records and token history | `queue:read` | Yes | Yes | Assigned visits | — |
| Issue tokens, recover tracking links and close sessions | `queue:create`, `queue:links`, `queue:close` | Yes | Yes | — | — |
| Queue states, call-next and station availability | `queue:update` | Yes | Yes | Own station and assigned visits | — |
| Visit-specific redistribution proposals | `queue:balance` | Yes | Yes | — | — |
| Register and read patients | `patient:register`, `patient:read` | Yes | Yes | — | — |
| Correct an existing patient identifier | `patient:update` | Yes | — | — | — |
| Appointments, booking risks, arrival slots, booking and cancellation | `appointment:read`, `appointment:book`, `appointment:update` | Yes | Yes | — | — |
| Create and revoke kiosk links | `kiosk:manage` | Yes | Yes | — | — |
| Department-level planning and prediction | `planning:read` | Yes | Yes | Yes | Yes |
| Waiting time, peak hours, forecasts and staffing simulation | `analytics:read` | Yes | — | — | Yes |
| Summary report exports | `reports:read` | Yes | — | — | Yes |
| Detailed visit exports | `reports:read` and `queue:read` | Yes | — | — | — |
| Model performance and service health | `performance:read` | Yes | — | — | Yes |
| Read alerts and staff notifications | `alerts:read` | Yes | Yes | Operational only | Operational only |
| Evaluate or resolve alerts | `alerts:manage` | Yes | — | — | — |
| Feedback summaries | `feedback:read` | Yes | — | — | Yes |
| Voluntary free-text feedback | `feedback:comments` | Yes | — | — | — |
| Import historical visits and read audit logs | `data:import`, `audit:read` | Yes | — | — | — |

Historical migration 013 granted `queue:check_in`. It remains in the database for migration compatibility. Current staff check-in APIs require `queue:create`.

## Ownership and permission errors

- FastAPI resolves each staff session to a current user and loads permissions from `role_permissions`. Migration [017](../database/migrations/017_staff_authorization.sql) defines the default grants. The [authorization helper](../backend/core/authorization.py) denies access when the grant is absent. JWTs carry identity and session claims. Scope grants come from PostgreSQL. The API runtime database role has read-only access to grants.
- Staff queue queries, counts and token history use the active doctor profile tied to the signed-in doctor. The doctor can call the next eligible unassigned visit by using their availability-checked station in the same queue transaction. Direct updates to an unassigned visit or a different doctor’s visit return `404`. Doctors receive queue and service details for assigned visits. The patient registry, internal priority notes and private tracking links require separate permissions.
- Patient tracking, appointment details, confirmation, notification preferences and feedback resolve a specific link to a specific record. Notification reads also check the notification audience and private owner. A kiosk link can issue a walk-in token for its department while it is active. Possession of a link confers the associated access, so staff should share it only with the intended recipient.
- Managers can monitor aggregate performance, run planning forecasts and export reports. Individual queue and registry access, imports, alert mutations and administrative actions are restricted. The queue event stream used to refresh performance figures carries an empty change event.
- Missing or invalid staff authentication returns `401`. An authenticated user without a required grant receives `403` with error code `forbidden`. Queue and patient resource endpoints use `404` for missing resources and ownership mismatches. The [API reference](API_REFERENCE.md) documents the shared error envelope.

Apply migrations before starting the API. The permissions in this matrix apply to both legacy browser routes and the versioned staff API. [Authorization tests](../backend/tests/test_authorization.py) cover the matrix, live grant changes, doctor assignments and patient link isolation.

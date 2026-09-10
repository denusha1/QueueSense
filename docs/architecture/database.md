# Database architecture

```mermaid
erDiagram
    users ||--o| staff : account
    departments ||--o{ staff : employs
    staff ||--o{ staff_schedules : scheduled
    staff ||--o{ staff_availability : availability
    departments ||--o{ queue_sessions : opens
    queue_sessions ||--o{ queue_tokens : contains
    staff o|--o{ queue_tokens : serves
    queue_tokens ||--o{ service_events : records
    queue_tokens ||--o{ predictions : estimates
    model_runs ||--o{ predictions : versions
    departments ||--o{ alerts : monitors
    users o|--o{ audit_logs : acts
```

PostgreSQL is the planned operational source of truth. Composite references prevent assigning a token or event to a different department's staff. Foreign keys restrict deleting referenced entities; there is no blanket cascading data deletion. Queue and event timestamps are validated by checks and triggers. Partial indexes support waiting tokens, completions and unresolved alerts; other indexes support department/date filters and latest staff/prediction lookups.

The Next.js dataset review reads the generated summary JSON at build time. This is explicitly a snapshot, not database health or live operations. Rebuild the frontend after regenerating a different snapshot.

Migrations run under one PostgreSQL transaction and advisory lock, with filename/checksum tracking. The seeder takes the same lock, refuses existing department data, and loads the entire SQL seed transactionally. Runtime application credentials/permissions will be introduced with authentication; the Docker database-owner credential is for local provisioning only.

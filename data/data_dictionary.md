# Data dictionary and operational contracts

All demonstration records are generated, fictional and non-identifying. There are no names, phone numbers, diagnoses, notes or medical histories. UUIDs are relational keys; `SYN-*` values are fictional visit identifiers, not stable patient identities. The initial dataset uses standard FIFO service only: expedited is a reserved queue category, not medical triage.

Every timestamp is PostgreSQL `timestamptz`; generated CSV timestamps carry `+05:30`. The department timezone is `Asia/Colombo`. A session's `service_date` is the date of arrival in that timezone. Units for all derived waits/service durations are minutes. All UUID primary keys have a database default; generator UUIDs use a fixed namespace for reproducibility.

| Table | Columns and meaning |
| --- | --- |
| users | `id`; lowercase unique `email`; required `password_hash`; `role` = admin/reception/doctor/manager; `is_active`; `created_at`. No accounts are seeded. Password hashing and server authorization arrive in step 3. |
| departments | `id`; unique uppercase `code`; unique `name`; fictional `location`; IANA `timezone`; positive `queue_threshold`; `is_active`. |
| staff | `id`; nullable unique `user_id` (demo clinicians have no accounts); `department_id`; fictional `display_name`; `staff_type` = doctor/service; `is_active`. |
| staff_schedules | `id`; `staff_id`; local `service_date`; `start_at`; `end_at` strictly after start; `status` = scheduled/cancelled. Generator emits two daily work intervals separated by lunch and explicitly extends the afternoon interval for any generated overtime. |
| queue_sessions | `id`; `department_id`; `service_date`; `opened_at`; nullable `closed_at`. One session per department/date. Seed sessions are all closed. |
| queue_tokens | `id`; composite `session_id`/`department_id`; nullable `staff_id` tied to the same department; positive `token_no` unique within session; `synthetic_patient_id`; `priority_class`; `status`; `check_in_at`; nullable `called_at`, `service_start_at`, `completed_at`, `ended_at`. |
| service_events | `id`; `token_id`; `department_id`; nullable `staff_id`; `event_type` = check_in/called/service_start/completed/cancelled/no_show; `event_time`. One event per type/token. Event time must equal the token's corresponding timestamp; staff must match for service events. |
| staff_availability | `id`; `staff_id`; `status` = available/busy/break/offline; `changed_at`. Generator supplies schedule-level availability (including lunch/offline), not a second copy of every consultation's busy/idle state. Busy intervals can be derived from token timestamps. |
| model_runs | `id`; `model_name`; unique `version`; `training_start`; `training_end`; finite nonnegative `mae` and `rmse`; finite `r2` ≤ 1; `created_at`. No fabricated model results are seeded. |
| predictions | `id`; `token_id`; finite nonnegative `predicted_wait_minutes`; `model_version` references a real model run; `predicted_at`. Empty until evaluated models exist. |
| alerts | `id`; `department_id`; `alert_type` = high_queue/delay/capacity/model_error; `severity` = info/warning/critical; `message`; `created_at`; optional `resolved_at` not before creation. |
| audit_logs | `id`; nullable `user_id` for a system action; `action`; `entity_type`; `entity_id`; `created_at`. Entity ID is intentionally polymorphic, with no cross-table FK. Audit service and access restrictions are future work. |
| schema_migrations | Infrastructure table created by the Python migration CLI: filename `version`, SHA-256 `checksum`, `applied_at`. Applied files must not be edited; add a new migration. |

## Queue states

- `waiting`: only arrival is known.
- `called`: assigned staff and call timestamp exist.
- `in_service`: call and service start exist; no end timestamp.
- `completed`: arrival/call/start/completion exist; `ended_at = completed_at`.
- `cancelled`: ended before consultation; a call may or may not exist.
- `no_show`: called by staff but never began consultation; an end timestamp exists.

Allowed updates: waiting → called/cancelled; called → in_service/cancelled/no_show; in_service → completed. Completed/cancelled/no-show records are terminal and immutable. Token identity and already-recorded timestamps cannot be rewritten. Historical inserts may enter any state if timestamp/state constraints pass. This importer capability must not be exposed to untrusted operational clients.

Database constraints cover references, department alignment, token uniqueness, timestamp chronology, session boundaries at token insertion/update, and event consistency at event insertion/update. They do not yet implement staff booking conflict prevention, row-level access policies, automatic event insertion, or revalidation after editing parent session records; API authorization and queue service transactions must supply these workflows. The current synthetic generator is separately tested for non-overlapping scheduled service. No app login uses the database-owner credentials.

## Metrics

`token_durations` calculates waiting = service start − arrival and service = completion − service start. Missing service timestamps produce NULL rather than zero. `daily_department_summary` groups by department and **arrival service date**; this is a cohort summary, not completion-hour throughput. Average/median/p90 ignore NULL values. True throughput by completion time and finalized cancellation/no-show rates are later analytics work. The review page averages completed waits and rounds once to one decimal place, consistent with the SQL validation.

## Generated files

`python3 data/generator/generate.py` writes seven CSVs plus `seed.sql` under ignored `data/generated/`. SQL strings are escaped; identifiers are fixed by the generator. These files are machine-generated input for a trusted local seeding tool, not a general user-upload importer. The committed `data/sample/summary.json` contains computed totals, three department summaries and up to 20 tokens per department from the latest operating date. The page reads this saved snapshot, with no database connection.

Defaults: start 2026-06-01, 90 calendar days through 2026-08-29, seed 42, generator version 1.0.0. Sundays closed. Demand varies by weekday, hour and department. Two or three clinicians operate per department/day, with 12:00–13:00 lunch; arrivals occur 08:00–16:00. Service durations follow capped log-normal distributions and occasional delays; cancellations/no-shows each occur with approximately 4% probability. Service is FIFO with no clinical priority logic. Shift lengths include any synthetic overtime explicitly, which is an assumption and not a staffing recommendation.

The SHA-256 fingerprint covers the complete canonical generated table data, not just the displayed sample. Repeatability is checked for the same parameters/runtime; keep the Python version fixed when comparing artifacts across environments.

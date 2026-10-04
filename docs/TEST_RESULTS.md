# Local verification results

- Native PostgreSQL 17.10: all five migrations applied; unchanged migration re-run passed; full synthetic seed loaded.
- Database integrity: 11 invalid writes rejected; valid queue lifecycle and rollback verified.
- API/model suite: 20 passed. Two dependency deprecation warnings in the test client; no failing tests.
- Generator suite: seven tests covering reproducibility, seed sensitivity, FIFO/lunch behavior, non-overlap/schedules, references/timestamps, summary parity and bounds.
- Browser suite: all 15 product views loaded without application/runtime errors; real UI check-in → call → start → complete; private patient page reflected completion; simulator, import validation and CSV/PDF downloads passed; viewport widths 375/768/1440 had no horizontal document overflow.
- Frontend: optimized Next.js production build and TypeScript checks passed.
- Dependency audit during frontend tooling installation: zero reported vulnerabilities.
- Model test set: MAE 7.1038 minutes; RMSE 14.0474; R² 0.8730. Operational baseline MAE 9.6164. Synthetic holdout only.

Not executed here: Docker build/Compose, hosted CI run, cloud deployment or real-clinic evaluation. No claim of those checks passing is made.

## Feedback, security, mobile/PWA and health — 4 October 2026

- Backend: 29 tests passed against isolated PostgreSQL schemas, with migration re-runs, seed integrity and runtime permission checks. New coverage includes completed-visit eligibility, anonymous capability access, rating/comment validation, concurrent duplicate rejection, private feedback metadata, role boundaries, cohort filtering, measured wait/rating correlation, notification delivery and model failure/degradation.
- Frontend: production build and TypeScript checks passed with Next.js 16.3.8. Dependency audit reported zero vulnerabilities after the patch upgrade.
- Chromium: `BASE_URL=http://127.0.0.1:3002 node frontend/tests/experience.cjs` passed. Verified feedback submission and persistence, manager feedback visibility, health probes, 375px layouts, installation manifest/icons, and generic offline navigation. Cache inspection contained only `/offline.html`, with no patient or API data.
- The review instance runs on frontend port 3002/API port 8002 because port 3001 belongs to a separate project. Its launch settings allow these origins and point the frontend to the corresponding API.
- Notification probes cover the application's PostgreSQL live-update transport. External email/SMS delivery and production hosting infrastructure are not configured.

## Role dashboards, live tracking, insights, audit, reports and monitoring — 4 October 2026

- Backend: all 41 tests passed, including existing authentication, arrivals, feedback and health coverage. Added checks for private patient queue counts during active service, eight report types in both formats, export filter/audit parity, latest pre-service prediction selection, MAE/bias/date filtering, audit actor/context filtering and role boundaries.
- Database: migration `008_audit_context.sql` applied and re-run safely. Verification confirmed the runtime role cannot update or delete audit records.
- Frontend: production build, TypeScript validation and whitespace checks passed. Negative prediction bias uses a chart scale supporting negative values.
- Chromium: `BASE_URL=http://127.0.0.1:3002 node frontend/tests/operational.cjs` passed. Covered patient entry without staff access, live status updates between independent patient/staff sessions, recommendations, observed prediction charts, eight report types × PDF/CSV, audit before/after details, staff role boundaries and 375px layouts.
- Review instance: http://127.0.0.1:3002, with its corresponding API on port 8002. Patient entry: `/patient`; staff sign-in remains at `/`.

## Doctor matching, load balancing, forecasting and staffing — 4 October 2026

- Backend: all 46 tests passed. New checks cover service/language/continuity matching, incompatible assignment rejection, earliest eligible queue selection, protected/non-standard visit exclusion, anonymous patient doctor-option privacy, zero-hour forecast normalization, sample-size gating, planning permissions, capacity boundaries, added/removed/zero staff and non-finite input rejection.
- Forecast arithmetic: verified weekday demand against a controlled three-day cohort with zero-arrival observations and checked the 80th-percentile staffing calculation at an exact capacity boundary.
- Frontend: production build and TypeScript validation passed. Forecast presets initialize staffing comparisons synchronously; doctor recommendations clear when requirements change.
- Chromium: `BASE_URL=http://127.0.0.1:3002 node frontend/tests/planning.cjs` passed. Covered doctor profile editing, matching, overload suggestions, private patient doctor options, insufficient-history and recorded-weekday forecasts, scenario addition/removal, requirement-aware check-in, role boundaries and 375/768px layouts.
- Forecasts are statistical operational estimates. Service profiles require clinic confirmation, load balancing stays within the same department with staff review, and simulations leave queues/schedules unchanged.

## Queue delay, appointment risk and smart automation

- Full local PostgreSQL verification: **52 passed**. Includes additive migration/re-run, existing integrity/runtime-permission checks, congestion before queue growth, appointment/walk-in de-duplication, zero-clinician handling, confirmation and scoped reads, reminder stages/grace-window outcomes, cancellation alerts, immediate token status alerts, recalculated waiting estimates, personal staff read receipts and worker-lock exclusion/release. Tests clear automation state and use schema-specific locks so isolated verification cannot block the review worker.
- `npm run build --prefix frontend`: production build and TypeScript checks passed.
- `BASE_URL=http://127.0.0.1:3002 node frontend/tests/automation.cjs`: passed. Uses the real scheduled worker to verify automatic reminders; checks confirmation/risk updates, future congestion from an arrival burst, staff inbox delivery, immediate patient call status, privacy-safe browser alert opt-in, worker health and 375px layouts.
- Existing `experience.cjs` and `planning.cjs` browser checks passed with the shared inbox: feedback/PWA/health, doctor matching/profile editing, forecasts, staffing comparison, role boundaries and mobile screens.
- Queue status and booking/cancellation notices are persisted in the change transaction. Automation runs every 30 seconds; inboxes poll every 15 seconds. Distinct reminder stages and state revisions prevent duplicate notifications. Database advisory locking prevents overlapping cycles for the same schema across API workers; heartbeat health reports stale/disabled workers.
- Predictions are explainable operational baselines. Appointment risk uses booking/confirmation/timing signals, is not a calibrated probability and never changes booked capacity or cancels a visit. An expired linked check-in window records an observed missed arrival; unrelated reception tokens cannot establish attendance for that booking. Browser alerts require opt-in and an open page. External SMS/email and closed-browser push are not configured.
- Review services were migrated, rebuilt and restarted on frontend **3002** / API **8002**, preserving other applications using port 3001. Browser checks create synthetic departments/bookings/visits only.

## Smart check-in, live queue and AI waiting-time prediction

- Full native PostgreSQL verification: **56 passed**. New coverage checks required priority authorization and role boundaries; expedited-before-standard ordering and order within priority; consistency of patient/staff positions; priority-aware doctor recommendations; private tracking QR origin/cache/privacy checks; public arrivals rejecting priority fields; deterministic live AI inference; retained initial predictions and actual waiting-time/error comparisons; unavailable clinician and model-failure fallbacks.
- `npm run build --prefix frontend`: final production build and TypeScript checks passed.
- `BASE_URL=http://127.0.0.1:3002 node frontend/tests/core-queue.cjs`: passed against the final restarted build. Verifies staff priority check-in, QR loading/copy, priority call-next, missed/called/in-service/completed states, private patient SSE updates, automatic prediction-performance refresh when service starts, actual-versus-initial wait displays and 375px layouts including long department codes.
- Existing `planning.cjs` passed after queue-order changes; `automation.cjs` passed with the shared live-prediction service, including automatic reminders, confirmation/risk updates, congestion warnings, inbox delivery and worker health.
- Initial predictions are retained at check-in; changing live estimates do not overwrite them. Monitoring evaluates the latest stored pre-service prediction or the retained snapshot, including operational fallbacks. Standard unrestricted queues use the existing synthetic-data Random Forest; priority/restricted queues use compatible-clinician capacity because the training features do not model those policies. Missing/failed/non-finite inference falls back safely; no compatible coverage returns an unavailable estimate.
- Migration `011_checkin_predictions.sql` was applied with runtime grants; the review API and final frontend build were restarted on **8002 / 3002**. Other applications on port 3001 were preserved. QR image checks wait for loading and clipboard checks explicitly grant browser permission. The mobile token heading now scales/wraps long department codes instead of overflowing.

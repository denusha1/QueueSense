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

## QueueSense visual identity and patient journey

- Added a shared connected-dot flow motif on the welcome page, workspace headers, QR tracking cards, patient token cards and trend charts. The welcome page illustrates the five-step care journey without presenting it as live data.
- Staff headers now use a compact layout; live/board screens show all five queue metrics in one desktop row. The live queue table begins within the first 850px of the desktop viewport in browser verification.
- Sidebar destinations are grouped into Daily operations, Insights and Administration using the existing signed-in role filters. Empty groups are omitted; mobile groups use the existing expandable menu, and navigation closes it after selecting a destination. Desktop navigation scrolls within the sidebar.
- Private patient pages place the token and next action before the journey. Current steps use `aria-current="step"`; mobile uses a vertical timeline. Called patients see a prominent navy next-step card. Missed/cancelled tokens stop at their appropriate stage and do not mark service/completion as reached.
- `npm run build --prefix frontend`: production build and TypeScript passed.
- `BASE_URL=http://127.0.0.1:3002 node frontend/tests/flow-design.cjs`: passed for shared motif, compact layout, grouped role access, mobile navigation, patient next-step visibility, called highlight, missed/cancelled progress and viewport overflow.
- Existing `core-queue.cjs` passed for priority/QR check-in, all live states, private tracking, automatic performance refresh and mobile layouts. Existing `experience.cjs` passed for feedback, health and PWA/offline behavior.
- Changes are limited to frontend presentation. The final review frontend was rebuilt and restarted on port 3002.

## Readable typography, semantic states and shared design tokens

- Consolidated palette, type sizes, spacing, radii and shadows into `frontend/app/design-tokens.css`; removed overlapping colour roots from legacy style files. Shared readability rules load after existing layouts.
- Body copy and table cells use 14px, form controls 16px, labels 12–13px and numeric values tabular figures. Desktop live queue controls stay on one row while mobile layouts retain wrapping.
- Queue badges and live metrics share amber waiting, blue called, teal in-service, green completed and muted red missed states. Checked-in appointments and service-health badges use the same semantic system. Five actual queue badges passed 4.5:1 text/background contrast verification.
- Prediction charts use solid navy actual waits and dashed lime predictions with a dark outline for visibility on white. Legends match the lines; keyboard readouts and series toggles remain functional.
- Production build and TypeScript checks passed. `readability.cjs` passed against synthetic real queue states and prediction chart data. `flow-design.cjs` passed for compact headers, first-screen live table, grouped role navigation and mobile/private patient journey. `premium-ui.cjs` passed for chart controls, reduced motion, pointer lighting, command navigation and all 16 workspace views at 375/768/1440px without page overflow.
- Final review frontend restarted on port 3002. Backend behaviour was unchanged by these presentation updates.

## Workspace chooser and sign-in presentation

- Redesigned the content below “Choose your workspace” with a two-column role card grid, role-specific tool chips, navy/lime selected cards and hover/focus treatment. Selecting a role updates a concise workspace description through a polite live region.
- Staff sign-in uses a dedicated form panel; demo access has its own panel and dataset link. Existing authentication, account-based authorization, password visibility and demo confirmation remain in place.
- Production build and TypeScript checks passed. Local Chromium checks passed for all four selections, dynamic descriptions/action labels, arrow-key radio navigation, password visibility, layouts at 375/768/1440px and manager demo sign-in. Screenshots were reviewed at desktop and mobile widths; no page or card overflow was observed.
- Review frontend restarted on port 3002.

## Staff sign-in card styling

- Added a navy gradient header with a shield icon, selected-role badge and decorative patient-flow motif. The light form body now uses larger icon fields, visible focus treatment, a styled password toggle, a readable account-access note and a lime action with a separate arrow.
- Production build and TypeScript checks passed. Chromium verified 320/375/768/1440px layouts without page/form overflow, role badge updates, password visibility and recovery messaging. An intercepted synthetic login verified the existing email/password/role payload and rejected-login recovery without sending credentials to the backend. Desktop and mobile form screenshots were reviewed.
- Review frontend restarted on port 3002.

## Welcome page background

- Added scoped navy/lime ambient lighting, a faint dot grid and decorative connected routes behind the welcome surfaces. The navy story panel has a subtle architectural grid and contour rings; the entry panel retains a light readable surface.
- Background layers are hidden from assistive technology and never capture pointer events. High-contrast and forced-colour modes remove the decorative patterns. The effects are static and introduce no motion or external assets.
- Production build/TypeScript and Chromium checks passed: 320/375/768/1440px without page overflow, contrast preference, role/password controls, demo dialog and patient tracking navigation. Desktop background screenshot reviewed. The updated review frontend runs on port 3002.

## Ten-row table pagination

- Added shared pagination to every rendered table: live tokens, appointments, generic analytics/report/schedule/import/feedback tables, users, model versions, hourly staffing recommendations, congestion horizons and demo sample records. Controls appear only above 10 rows; desktop has numbered pages and Previous/Next, with a compact page counter and 44px controls on mobile.
- Search/filter/sort changes reset the selected page. Live queue refreshes retain the current page; shrinking datasets clamp to the last valid page. Cell handlers and private patient links are preserved. Summaries distinguish filtered matches from visible rows; audit records retain the API's existing 200-record batches with clearly labelled batch controls and 10-row pages within each batch.
- Production build and TypeScript passed. `pagination.cjs` passed for 0/10/11/25 rows, boundaries, actions/private links on page 2, live refresh preservation, shrinking data, search/sort resets, responsive widths and dataset/analytics tables. `premium-ui.cjs` passed for all 16 workspace views at 375/768/1440px, mobile navigation and existing interactive controls. Desktop live-table screenshot reviewed.
- Final review frontend restarted on port 3002; no backend/API limits or export cohorts were changed.

## Personalised workspaces, loading states, patient freshness and reception quick desk

- Workspace preferences now provide favourite destinations, named filter presets (up to eight), and custom date ranges. Browser storage is scoped to account ID and role; saved destinations are restricted to the user's available navigation. Saved filters exclude private links, token searches and patient data. Doctor live metrics prioritise their assigned called/in-service patients.
- Initial/context loading shows accessible skeletons; background refresh retains existing data instead of clearing tables/charts. Errors include retry and explain when previously loaded information remains visible. Queue empty states offer clear-filter and authorised check-in actions. Reduced-motion mode disables skeleton animation.
- Patient tracking shows the last successful update, stale/error indication, manual retry/refresh, unavailable-position handling, recent distinct estimate ranges and increased-estimate notices. Ranges describe observed updates on the current page, not a calibrated prediction interval or guaranteed call window. Existing next-step prompts and live status transitions remain prominent.
- Reception/admin live screens include a collapsible quick desk for check-in with existing priority/service/language/continuity rules, token-search focus, clinician selection/call-next and token receipt reprint. Receipts retain private tracking QR/link controls; printing waits for QR decode and print CSS includes only the selected receipt. Closed desk layouts keep the live table in the first desktop screen.
- Production build/TypeScript and `workspace-upgrades.cjs` passed: controlled initial loading, persisted favourites/presets, custom ranges, synthetic reception check-in/call/search, private receipt and print-only PDF, patient freshness/range/called transitions, failed-refresh recovery and responsive layouts.
- Existing `flow-design.cjs`, `premium-ui.cjs` and `core-queue.cjs` passed for compact layout, grouped role navigation, private patient journeys, all 16 views at 375/768/1440px, priority queue order, QR/copy, automatic prediction monitoring and service transitions. Reception/patient screenshots were reviewed. Review frontend restarted on port 3002; backend authorization and prediction behavior were unchanged.
- Existing `pagination.cjs` also passed after the loading/preset changes: 0/10/11/25 rows, live page preservation/shrink clamping, filter/sort resets, private row actions and sample/analytics tables.

## Languages, external delivery, server paging, account security and fixed welcome panel

- Patient entry/tracking and public check-in support English/Tamil/Sinhala and persistent larger-text controls. Core journey/status, estimates, doctor options, feedback and notification settings use translated UI; clinic-issued notices/names remain in their original language.
- Verified, explicit opt-in email/SMS and browser Push subscriptions use encrypted destinations. SMTP/Twilio/Web Push adapters, generic lock-screen-safe messages, destination removal and a durable de-duplicated retry outbox are implemented. Real provider credentials are absent: mocked adapter/delivery tests passed; no live external delivery is claimed. Configuration and limits are documented in `docs/ACCOUNTS_AND_NOTIFICATIONS.md` and `.env.example`, including Docker environment passthrough.
- Live queue, audit and administration user tables load server-filtered ten-record pages. Counts and queue KPIs cover the full selected cohort. PostgreSQL coverage verifies 605 tokens, stable last-page boundaries, clamping, literal wildcard search, validated ordering/page sizes and role boundaries. Aggregate/other tables and the department board retain their documented existing endpoint limits.
- All staff roles have profile/session/password controls. Recovery hashes one-time, expiring codes and revokes old sessions. Personal administrators can enrol an authenticator; MFA confirmation revokes sessions and login rejects reused time steps. Demo credentials/MFA enrolment are protected. Sensitive secrets/passwords do not enter audit details.
- Desktop welcome uses a full-viewport blue story panel with no scrolling and an independently scrolling entry panel. Browser checks cover 600/720/900/1080px heights, content fitting above the footer, and normal 375px mobile scrolling. Mobile tracking spacing preserves first-screen next-step instructions.
- Final production build/TypeScript passed. Complete backend suite: **64 passed** against isolated PostgreSQL schemas. Dependency compatibility and `git diff --check` passed. Migration 012 and runtime grants applied locally; review API/frontend restarted on 8002/3002.
- `next-upgrades.cjs` passed: fixed desktop/scroll/mobile layout, persistent Tamil/Sinhala/larger text, translated private patient/public kiosk screens, server paging/search/full counts, explicit unconfigured-provider states, account profile/session UI, personal admin MFA enrolment and sign-in, recovery page, and no browser errors.
- `pagination.cjs`, `flow-design.cjs` and `workspace-upgrades.cjs` passed with asynchronous server-page assertions/interceptions. Coverage preserves 0/10/11/25 rows, page-two private links/actions, refresh preservation and shrink clamping, filter resets, grouped role navigation, compact queue table, patient called/missed/cancelled journeys, reception check-in/receipt print, browser preferences and failed-refresh recovery. Welcome and mobile patient screenshots were inspected.

## Department queue board pagination

- Board cards now use shared page controls, showing ten filtered tokens per page. Controls appear only above ten results, preserve patient links/actions, reset on department/search/status/order changes, and retain/clamp the selected page during live refreshes. The existing board endpoint's 500-token limit remains.
- Production build/TypeScript and extended `pagination.cjs` passed. Browser coverage includes 24 active cards over three pages, page-two private links, filter/search resets, shrinking to 11/10/0 records, page clamping, empty states, and mobile Previous/Next controls without horizontal overflow. Existing live, sample and analytics table pagination passed in the same run. Local frontend restarted on port 3002.

## Enterprise authorization and API hardening

- Native PostgreSQL verification passed all 138 backend tests on 25 November 2026. This also verified migration 017, migration re-run, data integrity and restricted runtime database grants. PGlite verified migrations 001 through 017, historical record preservation, KPI parity, constraints and rollback.
- Next.js 16.4.6 built successfully and passed TypeScript checking. Eight Playwright checks passed across product views, arrivals, core queue, planning, v1 runtime credentials, proxy errors, JWT renewal and operations/reporting. The browser runs used the locally cached Chromium headless build 1254 with Playwright 1.63.0 because the matching build download was still in progress.
- A separate local fixture confirmed both Next.js proxies reject an upstream HTTP 200 HTML response and allow QR SVG with the API content policy. The proxy error regression now runs in CI when the workflow is executed.
- After updating the affected packages, npm and PyPI scans reported zero advisories for the frontend, database test and backend lockfiles. See the [security audit](SECURITY_AUDIT.md) for scope and remaining risks.

## Traffic management and publication preparation

- Backend verification passed all 147 tests against local PostgreSQL. Migration 018 applied and re-ran cleanly. Tests verified concurrent request accounting, reset behavior, staff and capability isolation, and HTTP 429 with `Retry-After` for the partner origin. The restricted API database role also enforced a quota in a rolled-back smoke transaction. PGlite verified all 18 migrations.
- Both OpenAPI files passed validation and generation drift checks. The measured, suppressed and 429 examples match the schemas. The generated Postman collection passed the Postman v2.1 schema check, and the Choreo Git metadata points to the one-operation publication contract.
- The additional HTTPS 429 pass-through smoke was blocked by the automatic approval review usage limit. Choreo organization access, live gateway policies and Developer Portal publication remain pending.

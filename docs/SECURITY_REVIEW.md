# QueueSense security review

Review date: 5 October 2026  
Scope: repository implementation and recorded local verification. This is a project-level review, not an independent penetration test or production certification.

## Findings

| Area | Evidence in this repository | Assessment / follow-up |
| --- | --- | --- |
| Authentication and sessions | Argon2id hashes; opaque random session cookies stored as hashes; expiry, revocation and account deactivation; optional administrator MFA and recovery codes. | Implemented. Keep HTTPS enabled in production and protect recovery/MFA secrets. |
| Authorization and request origin | Server-side persisted role checks; exact allowlisted Origin for mutations; Next.js auth proxy forwards fixed routes. | Implemented. Keep the API private behind the frontend and configure exact production origins. |
| Throttling | Failed login attempts are limited per account and backend peer in PostgreSQL. Public QR arrivals also have a per-code limit. | Implemented, with a known boundary: the peer limit behind the proxy is shared, not per-client IP. Configure a trusted edge rate limiter before public deployment. |
| Input validation | Request schemas bound lengths, numeric ranges, formats and CSV size/row counts; database constraints protect queue invariants. | Implemented. Keep schema and migration changes covered by automated checks. |
| Audit trail | Queue mutations and audit entries commit together; sensitive credentials, comments and private links are excluded; runtime role cannot update/delete audit rows. | Implemented. Define retention and access policy before handling real patient data. |
| Browser protections | Referrer suppression, frame denial, production HSTS, no-store responses for sensitive routes, and service worker excludes patient/API data. | Implemented. Review reverse-proxy headers and logs too; redact private patient-link paths. |
| Dependencies | `docs/TEST_RESULTS.md` records a frontend dependency audit with zero reported vulnerabilities during the documented installation. | Point-in-time result only. Repeat dependency scans on each release; this review did not run a fresh scanner. |
| Backups and recovery | Deployment notes require PostgreSQL backups, but no automated backup/restore job or recovery evidence is included. | **Open operational gap.** Follow `docs/BACKUP_RESTORE.md`; schedule backups, protect them, and rehearse restoration in a separate database before deployment. |
| Deployment assurance | Existing docs state Docker/Compose, hosted CI and cloud deployment have not been verified. | Do not describe the app as production-secure or publicly deployed. Complete deployment-specific review and recovery drills first. |

## Verification evidence and limits

The project records backend tests for authentication, cross-role denial, origin rejection, throttling, validation, security headers, audit permissions and account recovery/MFA; see `docs/TEST_RESULTS.md` and `backend/README.md`. The repository also contains `.github/workflows/ci.yml`. This document maps those recorded checks to security controls; it does not claim a fresh test run, external audit, live dependency scan, penetration test, backup restore, or cloud verification.

## Release checklist

- Set `APP_ENV=production`, disable demo login, use HTTPS and exact HTTPS origins.
- Keep PostgreSQL and FastAPI on a private network; use the restricted runtime database role.
- Configure a trusted edge rate limiter and redact private patient-link paths in proxy logs.
- Configure encrypted, access-restricted backups and complete a restore rehearsal.
- Re-run dependency scanning and CI on the release commit; record dated results.
- Use synthetic data for public demos. Complete privacy, retention, consent and incident-response review before using real patient data.

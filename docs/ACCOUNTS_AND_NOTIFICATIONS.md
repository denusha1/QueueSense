# Accounts, patient languages and external notifications

The patient entry, queue tracker and public check-in pages have English, Tamil and Sinhala controls and a larger-text option. Preferences remain in the browser; tracking links and contact details are not stored in these preference keys. Clinic names, clinician names and clinic-issued notices retain their original language. Patient language controls do not translate the staff workspace. A native-speaker review of translations is recommended before clinical rollout.

Every staff role has **My account** in its navigation. It includes a display name/language preference, active session listing and revocation, password change, and verified notification preferences. Password change revokes other sessions. Shared demonstration credentials cannot be changed or used to enrol MFA or issue staff recovery codes.

**Forgot password?** opens `/recover`. Eligible staff can request a 15-minute recovery code through configured SMTP email, or receive a code privately from a personal administrator after identity verification. Unknown and ineligible accounts receive the same response. Codes are stored as hashes, expire, and are consumed once; resetting the password revokes all sessions. An enrolled authenticator is still required during recovery. Losing the authenticator requires an administrator-supported recovery procedure outside this self-service workflow; there are no MFA bypass or backup-code controls in this release.

Administrators can enrol a standard time-based authenticator in **My account** using a setup key. Pending setup expires in 10 minutes. Confirmation revokes all sessions. Sign-in, sensitive account changes and recovery require a fresh six-digit code; accepted time steps cannot be replayed. Sign-in expands **Use an authenticator code**. The implementation follows [RFC 6238](https://www.rfc-editor.org/info/rfc6238/).

## Provider configuration

Configure the API environment, not browser source code. `.env.example` lists the names and Docker Compose passes them to the API. Do not paste secrets into chats or commit `.env` files.

- `ACCOUNT_ENCRYPTION_KEY`: a stable Fernet key, required for encrypted account secrets/destinations in production. Generate privately with `cryptography.fernet.Fernet.generate_key()` and retain it securely between deployments. Changing or losing it makes existing encrypted MFA/notification records unreadable. Local development uses an ignored, mode-0600 `.local/account-key`; containers should use an explicit persistent environment key.
- Email/recovery: `SMTP_HOST`, `SMTP_PORT` (587 by default), `SMTP_FROM`; optional `SMTP_USER`/`SMTP_PASSWORD`. STARTTLS is used by default. Set `SMTP_SSL=true` and typically `SMTP_PORT=465` for implicit TLS.
- SMS: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`. Numbers use international `+` format.
- Background push: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`. Supply a matching VAPID pair in the formats accepted by [pywebpush](https://github.com/web-push-libs/pywebpush). The public key must be URL-safe base64 of the uncompressed P-256 public key. HTTPS and browser/platform Web Push support are required; localhost supports development. An explicit browser gesture requests permission.
- Keep `ENABLE_AUTOMATION=true` to run notification generation and delivery every 30 seconds. `PUSH_ALLOWED_HOSTS` can add trusted providers; the default allowlist covers Chrome/Firefox/Apple push hosts.

Email/SMS setup requires explicit consent and a destination verification code. Unverified targets receive no clinic updates. Codes expire in ten minutes and allow at most five attempts. Destinations and push subscriptions are encrypted; response metadata contains only masked addresses. Patients use their private capability link to manage only their own token's preferences; appointment preferences are scoped similarly. Staff targets belong to the signed-in user. Removing a target removes queued deliveries to it.

External messages are generic. They contain no medical details, token identifier or private tracking link, including on a lock screen. Push opens the generic patient entry or staff sign-in page. Existing in-app messages remain visible and page-open browser alerts remain separately selectable.

A PostgreSQL outbox de-duplicates each notification/destination pair, retries failures up to five times with backoff, and stores only an exception type for failures. Older messages do not replay after opt-in or a changed destination is re-verified. Delivery is at least once: a provider accepting a message immediately before a worker/database failure can cause a repeated generic message. No live SMS, SMTP or Web Push provider deliveries have been tested in this local environment; adapter behavior is verified with mocks.

## Data paging

Live queue, audit history and the administration user table use server filtering/counting and 10-record pages, with stable ordering and page clamping. Queue KPIs describe the full department cohort, not the visible page. API page size is bounded at 50. Token/department search treats `%`/`_` literally. Queue estimates use the full eligible active working set even while only ten rows are returned. Sorting by computed live wait also loads the matching working set to rank it and can be more expensive than arrival/token ordering. This change does not introduce cursor paging or a prediction cache.

Other tables retain shared ten-row client pagination over their existing endpoint limits or aggregated datasets. The department board loads its existing maximum of 500 tokens and displays filtered active tokens in ten-card pages with shared Previous/Next and numbered controls. Filter changes reset the board to page one; live updates retain the page and clamp it when results shrink. Clinician account options are restricted to active, unlinked doctors, with at most 200 options.

## Welcome layout

At desktop widths of 1000px and above the welcome story's blue panel occupies the viewport height and does not scroll. The right entry panel scrolls independently, including keyboard focus navigation. Short desktop heights simplify the decorative story content. Mobile/tablet layouts retain normal document scrolling.

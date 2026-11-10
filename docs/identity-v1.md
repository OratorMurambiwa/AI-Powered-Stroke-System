# Shared identity authority v1 — Milestone 2A

## Boundary and identifiers

The TypeScript booking backend is the authority for **new shared identities**, staff roles, passwords and revocable sessions. The canonical roles are `patient`, `doctor`, `technician`, `admin`. Legacy `physician` is normalized to `doctor` on identity responses and authorization, without bulk updates to stored roles. An authorized admin may supply that alias during staff provisioning; the new record stores `doctor`. Public registration never accepts any staff role or role change.

The authority's immutable MongoDB `_id` string is `subject`, scoped by issuer `urn:stroke-platform:identity:v1`. It is an identity identifier, **not** a clinical patient ID. Names, emails, SQLite integers and `P###` codes are not identity joins. Duplicate emails cause a conflict; provisioning cannot convert a patient with a matching email into staff. No existing SQLite/MongoDB user, scan, clinical record or weight is imported, linked, normalized in bulk, or deleted.

The current Streamlit app remains a **separate legacy authentication domain**: it checks SQLite bcrypt/legacy SHA-256 credentials and stores role/user in Streamlit session state. Its doctor/physician synonym remains for legacy navigation only. No Streamlit cookie, session state, username, `X-User-Role`, patient code or role-selection page is accepted as booking authentication. The legacy signup guard and default-user prohibition from milestone 1 remain unchanged. No clinical API or new clinical access is introduced in 2A.

## Least-privilege matrix

| Operation | Patient | Doctor | Technician | Admin |
| --- | --- | --- | --- | --- |
| Own principal, own sessions, logout/password change | Yes | Yes | Yes | Yes |
| Public availability reads | Yes | Yes | Yes | Yes |
| Publish/edit/delete owned unbooked availability | No | Yes | No | No |
| Book appointment | Own patient identity only | No | No | No |
| Read/cancel appointment | Own appointments only | Assigned doctor only | No | No |
| Provision/change/revoke staff | No | No | No | Yes, current password + reason |
| Read identity audit events | No | No | No | Yes |
| Read clinical records / execute treatment | No new access in this milestone | No new access | No new access | No new access |

Admins manage identity; that role does not grant blanket appointment/clinical visibility. Technician is reserved for future assigned assessment operations, with no current appointment privileges. Appointment details return 404 for another patient's or unassigned doctor's identifier; list filters cannot override authenticated ownership. A future clinical API must implement its own explicit patient/encounter assignment checks and may not infer permission from role alone.

## Sessions and authentication

Canonical prefix: `/api/v1/identity`. Legacy `/api/auth/*` URLs remain aliases to the **same implementation and session store**, not a second credential authority.

| Method and path | Behavior |
| --- | --- |
| `POST /auth/register` | Patient-only `{email,name,password,role?:"patient"}`; creates identity/session/audit atomically |
| `POST /auth/login` | `{email,password}`; creates a new persisted session and audit event after password verification |
| `GET /me` | Live canonical identity principal |
| `GET /sessions` | Own active session IDs/issue/expiry times; no other users' sessions or raw JWTs |
| `POST /auth/logout` | Revoke current session |
| `POST /auth/logout-all` | Invalidate all own sessions and outstanding recovery material |
| `POST /auth/password/change` | `{currentPassword,newPassword}`; recheck password, change hash and invalidate every session/challenge atomically; login again |

JWTs use HS256 with a private, operator-generated signing secret, fixed issuer and audience `urn:stroke-platform:booking:v1`, `ver=1`, `sub`, random UUID `sid`, integer `iat`/`exp`. They contain no authoritative role claim. A supplied token role is ignored; current database role is authoritative. `JWT_TTL_SECONDS` is validated as an integer **60–900 seconds** (default 900); no refresh token or unbounded expiration. Old milestone-1 JWTs are deliberately rejected; users must log in again. Issuer/audience/algorithm/required claims/lifetime and persisted issue/expiry times are checked.

Every authenticated request checks the live user and persisted session, current role, account state and credential version. Expired records are rejected even before MongoDB TTL cleanup. Logout, password change/recovery, staff role changes and revocation invalidate sessions durably. Login and sensitive mutations write the user within their transaction so concurrent revocation cannot race a new committed session or protected booking write. Read requests already authorized before revocation may complete; there is no retroactive cancellation of in-flight reads. Store outages fail closed. The database must be a replica set and required indexes must initialize before listening.

## Staff lifecycle and audit

No HTTP bootstrap endpoint, public staff signup or default administrator/password exists. New staff records are `invited` with an unexposed random unusable credential until the recipient sets their own password using an activation token. Only an active admin with a live session **and current password recheck** can perform:

- `POST /staff`: `{email,name,role,reason,currentPassword}`. Canonical staff roles only (plus physician alias). Returns `{schemaVersion:1,user:{id,role,state},deliveryId}`; no activation token/password.
- `PATCH /staff/:id/role`: `{role,reason,currentPassword}`. Staff-only targets, invalidate all sessions/challenges. Role change is not patient promotion.
- `POST /staff/:id/revoke`: `{reason,currentPassword}`. Retains the user, marks `revoked`, invalidates sessions/challenges/delivery envelopes; login and recovery cannot reactivate the account.
- `GET /staff/:id/audit`: newest 100 identity audit events for that subject; admin only.

An admin cannot revoke or change their own role. A persisted governance lock serializes staff management and rechecks the acting admin inside the transaction, preventing concurrent mutual revocations from removing every active admin. Existing patient/appointment data is retained. New bookings recheck and serialize with the clinician identity: retained slots for revoked or reassigned doctors cannot be booked. Revocation does not automatically cancel existing appointments; operational reassignment/cancellation is a separate human action. No staff deletion or implicit reactivation exists. An invited account whose role changes must request a new recovery/activation handoff because the old token is invalidated.

Bootstrap is an **explicit local operator action**, with database access and `ALLOW_IDENTITY_BOOTSTRAP=true` in that CLI process only:

```sh
cd booking-backend
npm ci && npm run build
# Provide private JWT_SECRET / IDENTITY_DELIVERY_KEY / synthetic-only MONGODB_URI.
ALLOW_IDENTITY_BOOTSTRAP=true node dist/identity/operator.js bootstrap
```

Prompts request operator reference, new admin email/name, and authorization/change reference. No password is accepted in command arguments. Bootstrap creates an invited admin, encrypted activation envelope and audit event atomically. It is refused if the persisted one-time marker is closed **or any admin already exists**, including a retained revoked admin. Concurrency cannot provision two bootstrap admins. It is not an account takeover/recovery backdoor. Ordinary server startup never seeds an account or mutates existing identities into admins. A hospital must authorize the operator and verify staff qualifications; code cannot verify clinical credentials.

Security changes and successful provisioning/revocation/activation, login success/failure, session invalidation, password recovery and operator handoff append timestamped audit events with actor/subject/action, bounded reason and before/after roles where applicable. Tokens/passwords/emails/request payloads are not audit fields. Relevant audit writes share the security-change transaction; audit failure rolls back the change. There is no audit update/delete API. Database administrators can still modify collections; this is application-level audit history, not a tamper-proof compliance archive. Rejected admin operations do not currently produce a separate denial audit event.

## Password recovery and local delivery

- `POST /auth/password-recovery/request` with `{email}` returns the same generic **202** response for known, unknown, invited and revoked accounts. It never returns a token/user/delivery ID. A 250ms minimum response duration reduces basic timing differences, without claiming timing indistinguishability under load. Per-IP requests/reset attempts are limited to five per 15 minutes; issuance for the same account is limited to once per minute.
- For eligible accounts, a 256-bit CSPRNG token is stored as a SHA-256 hash with a **15-minute** expiry and credential version. Issuing a newer token invalidates older challenges/envelopes. A request alone does not change passwords or invalidate current sessions.
- The private local delivery queue stores recipient/token/purpose only inside AES-256-GCM ciphertext, using a separate required 32-byte `IDENTITY_DELIVERY_KEY` (64 hex characters), random nonce and envelope-ID/hash AAD. No plaintext token is stored, logged or exposed through HTTP. TTL cleanup is supplementary to explicit expiry checks.
- An authorized local operator reads pending delivery IDs from the private `identitydeliveries` collection and runs `node dist/identity/operator.js deliver`. The operator supplies the ID and reference, verifies the pre-registered recipient and secure independent channel, then types `HANDOFF`. The CLI decrypts once, clears the envelope and audits handoff in one transaction. Its **one-time stdout contains sensitive delivery material**: use a private terminal; never redirect it to logs, chat or Git. Handoff is manual/local; no actual email/SMS/provider is connected. For provisioning/bootstrap the delivery ID is also returned to the authorized actor; public recovery does not reveal it.
- `POST /auth/password-recovery/reset` with `{token,newPassword}` consumes a live version-matched activation/recovery token once, changes the bcrypt hash, activates an invited identity, invalidates all old sessions/challenges/envelopes and audits in one transaction. Revoked users are ineligible. Concurrent reset/handoff attempts admit one winner. Invalid/expired/replayed tokens return 400. Reset does **not** log the user in automatically.

Passwords need at least 12 characters and at most 72 UTF-8 bytes (bcrypt limit); login uses a random dummy bcrypt hash for unknown users. The manual operator must not accept an unverified caller's claimed name/email as identity evidence. Production recovery needs a reviewed side-channel transport, key storage/rotation and delivery custody procedures. Losing the delivery key makes queued envelopes unreadable; generate new challenges after an authorized key rotation. Losing all admin access requires an explicit separately reviewed recovery procedure, not rerunning bootstrap.

This design follows the relevant principles in [OWASP password recovery guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) and [OWASP JWT revocation guidance](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_Cheat_Sheet.html); test evidence is not a security certification.

## Future Python clinical identity contract

`booking-backend/contracts/identity-v1.schema.json` defines the closed principal response from `GET /api/v1/identity/me`; `introspection-v1.schema.json` defines `POST /api/v1/identity/introspect`. All identity/auth responses use `Cache-Control: no-store`.

The future Python API must explicitly forward a caller's bearer token to the authority's introspection endpoint with an empty JSON object. Success is HTTP 200 and `{active:true,schemaVersion:1,issuer,subject,role,sessionId,expiresAt}` matching that versioned schema. Invalid/revoked/expired credentials return 401; service/database errors return 5xx. Reject all non-200, malformed/wrong-version/wrong-issuer responses and expired principals. Do not cache positive responses across requests if immediate revocation is required, and never fail open on authority/network errors.

The Python service must not receive the HMAC signing key, mint sessions, decode a JWT as sufficient authentication, accept role headers, or trust a client-supplied introspection response. In production, use an authenticated protected service-to-service transport (TLS/service identity) with an explicitly configured authority URL, never a URL from the caller. This local milestone binds the authority to loopback; production transport/service credentials are not deployed here.

An introspected principal is identity only. Before accessing a clinical patient/scan/encounter, require an approved explicit subject-to-clinical-record mapping and per-record assignment checks. Missing mappings must fail closed. No mapping API/table, auto-link, Streamlit adapter or clinical endpoint is implemented here, and an existing Streamlit session is not such a mapping. Breaking changes require `/api/v2/identity` and a new schema ID; future optional extensions must be explicitly versioned because schemas reject extra fields.

## Remaining work

Shared portal/clinical API, explicit patient linkage, clinical record ownership review, browser integration, production TLS/service authentication, MFA/step-up beyond password recheck, distributed rate limiting, approved email transport and key/backup/retention procedures remain future work. Rate limits are per process/IP, not a distributed brute-force defense. No clinical data/inference or hosted model call was used for this milestone. Stroke predictions/treatment suggestions remain experimental and require clinician review.

## Milestone 2B clinical extension

The original `/introspect` and `/me` schemas above remain unchanged. New clinical consumers use `/api/v1/identity/clinical-introspect`, a separate closed v1 proof containing the same live principal plus `roleVersion`. Staff role changes/revocation advance that generation; ordinary password/session lifecycle operations do not. This prevents stale mappings/assignments from reviving after a role round trip, without binding durable linkage to one login session.

[Clinical linkage v1](clinical-linkage-v1.md) defines the explicit synthetic-only record registry, local operator-approved mappings and encounter assignments. The new Python read paths validate live authority proofs and deny admins clinical data. No existing SQLite account or Streamlit session is linked automatically. The 2A statements above describe its original scope; 2B adds these isolated paths without integrating or migrating the legacy app.

## Milestone 3 booking authorization

[Appointment/encounter v1](appointment-encounters-v1.md) adds a separate live reservation proof for the assigned doctor, bound to appointment/request/command hash/session and current role generation. Identity proofs alone do not create clinical access. Emergency creation requires a local operator-approved patient intake grant; admin identity remains insufficient. Existing identity response shapes and session lifecycle are unchanged.

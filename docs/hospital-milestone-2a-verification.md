# Milestone 2A verification — 2026-11-09

Baseline: stroke repository commit `850c4d5bb9ab61e69a6a0960212160e6f5cb7527`. Scope is the booking authority's identity/session/staff/recovery boundary, not a deployed clinical API or shared portal. See [identity v1](identity-v1.md) for endpoint contracts, role permissions, operator procedures and limitations.

## Executed checks

| Check | Result |
| --- | --- |
| `bash booking-backend/scripts/test-docker.sh` | Fresh private tmpfs MongoDB replica set; locked `npm ci`, strict TypeScript build, all HTTP/database/CLI tests and full dependency audit passed |
| Existing booking regression suite | **14 scenarios passed**: signup/login, validation, role checks, overlap/ownership, six-way slot contention, cancellation/rebooking, unique-index enforcement, storage rollback and edit/delete races |
| New identity suite | **26 scenarios passed**: actual MongoDB sessions, staff onboarding/activation/role changes/revocation, recovery, JWT validation, ownership/contract checks and actual compiled operator CLI |
| Node TAP totals | **42 passed, 0 failed, 0 skipped**; includes the two parent tests. Meaningful child scenario count is **40** (14 + 26) |
| `python3 -m unittest discover -s tests -v` | **4 passed**; existing public registration/default-user protections remain covered without importing the hardcoded clinical DB/UI stack |
| `python3 -m compileall -q app.py core models pages services` | Syntax compilation passed; not runtime/clinical integration verification |
| `bash -n booking-backend/scripts/test-docker.sh` | Passed |
| `git diff --check` | Passed |
| `npm audit` | **0 reported vulnerabilities** in the unchanged locked production/development dependency set; not a penetration-test or production-security certification |

## New identity evidence

- An explicit opt-in is required for local CLI bootstrap. Two concurrent bootstrap attempts create one invited admin; the persistent marker and existing-admin check prevent reruns. Initial credentials are not known defaults. The actual compiled `operator.js` was exercised in a separate synthetic database for bootstrap, one-time encrypted delivery and denied delivery replay.
- All public staff roles (`doctor`, `physician`, `technician`, `admin`) and extra privilege fields are rejected. Only an active admin with current-password recheck and bounded reason provisions staff. Duplicate patient email is a conflict, never promotion or linkage. New physician input becomes doctor; an existing synthetic physician row remains unchanged while authenticating with canonical doctor permissions.
- Staff activation cannot log in before a recipient chooses a password. Revocation invalidates every session and outstanding recovery/activation material and blocks login/recovery; invited-user revocation prevents activation. Role changes invalidate old sessions. Technicians/admins cannot read appointment content or perform doctor/patient booking actions. Retained availability for a revoked or reassigned doctor rejects new bookings and rolls back the slot claim, while preserving user/slot records.
- Self-revocation and self-role changes are rejected, including **uppercase ObjectId variants**. The casing regression was added after review identified a potential bypass of the initial string comparison. Concurrent admins revoking each other leave one active admin and return one success/one invalidated-session response.
- JWT issuer, audience, HS256, version, subject/session, required timestamps, maximum lifetime and live stored session issue/expiry are checked. TTL configuration outside 60–900 integer seconds fails startup; missing delivery key fails startup. Old milestone-1 JWTs and unknown-session tokens are rejected. A forged role claim does not change persisted patient privileges. Streamlit-style cookies, role headers and JSON session data grant no access.
- Logout affects one session; logout-all affects every session for that user without affecting another patient. Password change requires the current password and invalidates all sessions. Expired stored sessions fail before TTL deletion.
- Recovery returns the same generic 202 response for known/unknown accounts, never a token, and does not log out the user just for requesting recovery. Per-IP attempt limits and per-account issuance cooldown are tested. Timing indistinguishability under load is **not** claimed.
- Only a token hash and authenticated encrypted delivery envelope are stored; successful handoff clears ciphertext and is single-use. Tampered ciphertext authentication fails. Tokens expire after 15 minutes and are consumed once, including concurrent reset attempts. A newer request invalidates an older challenge. Reset invalidates all old sessions, preserves identity/role, and never automatically logs in. No raw token/password/email appears in generated audit events.
- Injected session-store failure denies access. Injected audit failure rolls back login/session creation, staff provisioning, revocation and password recovery/token consumption. After rollback, original state/session remains valid. These are explicit fault injections around real MongoDB transactions, not claims that the DB was physically stopped.
- Another patient cannot fetch an appointment detail, cancel it, override ownership through list filters, or enumerate the owner's session. Only the assigned doctor can view the appointment. Identity response keys/types/roles and introspection output are checked against the versioned contract fields. Client-supplied introspection fields and missing bearer credentials are rejected.

## Test isolation and data preservation

The test helper owns a run-specific Docker network and MongoDB 8.0.17 replica set, with no published ports. Both database/config directories use tmpfs; no existing data volume is mounted. Booking, identity and CLI scenarios use separate private synthetic databases in that fixture. Only synthetic `example.test` users, synthetic passwords/change references, random runtime keys and 2099 appointments are used. The helper removes only its own containers/network, without volume removal/pruning. Existing IncidentIQ/Compose services and host PostgreSQL port are unchanged.

No application dependency was added/upgraded; the milestone-1 npm lockfile is unchanged and was reinstalled with `npm ci`. Toolchain: Node 22.14.0/npm 10.9.2, TypeScript 5.9.3, Express 4.22.3, Mongoose 8.24.8, jsonwebtoken 9.0.3, bcryptjs 2.4.3, Supertest 7.3.2, MongoDB 8.0.17. The pinned Mongo digest remains in the helper. No host Node installation was required.

The source Hospital-booking-system repository is not modified/pushed. Changes are prepared in the separate stroke checkout, preserving the original local working copy. No SQLite/MongoDB patient/user store, uploaded scan, model weight, notebook, actual `.env` or credentials are staged. The historical `data/` Git tree remains unchanged. New runtime data is confined to the tmpfs fixture; there is no automatic migration/account linkage or current-account reset. Synthetic fixture updates used to test expiry/cooldown are test-only.

## Unresolved / unverified

- There is no shared frontend, clinical API, patient-ID mapping or automatic connection to Streamlit. Its SQLite login/session remains an isolated legacy domain and its old stored credentials are not rotated here. Clinical ownership review is future work; booking appointment ownership tests do not prove clinical-record authorization.
- No real patient data, upload, hosted AI request, model inference, clinical accuracy study or clinician workflow/browser test was run. Predictions and treatment suggestions remain experimental and require clinician review.
- Recovery/activation **delivery is manual via a private local operator CLI**, with an encrypted queue and no enabled email/SMS sender. Identity proofing, recipient verification and custody are operator responsibilities. Transport automation, secure key rotation/backup and lost-admin recovery need separate approval/design. No reactivation endpoint or refresh token is implemented.
- Production TLS/service authentication, MFA, distributed rate limiting, independent penetration testing, operational audit retention/tamper resistance and clinical/privacy review are not verified. Audit records are application-append-only; database administrators remain privileged. Denied admin requests currently lack a separate denial audit event. The 250ms recovery minimum is not a timing side-channel proof.
- Requests already authorized for reads before revocation can finish. Future Python services must use live authority introspection, reject failures, and enforce explicit per-record mappings/assignments; sharing the HMAC secret or trusting caller-provided roles/principals is forbidden by the contract.

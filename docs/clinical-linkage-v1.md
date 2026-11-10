# Explicit clinical linkage v1 — Milestone 2B

## Scope and separation

`clinical_api/` is a new, isolated Python 3.12 standard-library boundary. It does not import legacy `core`, SQLAlchemy models, Streamlit, scan services, ML weights or hosted AI clients. Booking remains the shared identity authority. Existing Streamlit credentials/session state and the original `data/stroke.db` are neither read nor trusted by these paths.

This milestone deliberately accepts **new, explicitly marked synthetic sources only**. It is not a migration/import tool and must not be pointed at an existing patient store. No existing SQLite/MongoDB records, scan, password or model weight is examined, normalized or updated by the implementation/verification work. The source booking repository is preserved.

There are three separate stores during integration tests: the private synthetic MongoDB authority; a freshly generated synthetic clinical SQLite source; and a distinct SQLite linkage/audit store. Only the first two contain synthetic user/clinical fixtures; the linkage store contains explicit IDs and approvals, not copied patient payloads or passwords. There is no cross-database transaction claim.

## Stable identifiers and explicit approval

The authority identity key is `(issuer, subject)`, with issuer `urn:stroke-platform:identity:v1` and the immutable lowercase Mongo ObjectId string. Clinical people and encounters use canonical UUIDs from an explicit source catalog, scoped to an immutable source UUID. Integer `patients.id`, `users.id` and `visits.id` are only native record references. They are never public API patient/encounter identifiers.

A new source must contain:

- Exactly one `clinical_source_metadata(source_id, synthetic, schema_version)` row matching the configured UUID, `synthetic=1`, `schema_version=1`.
- `clinical_record_ids(kind, native_id, record_uuid)` with unique, immutable record UUIDs and a unique `(kind,native_id)`. Kinds are `patient`, `staff`, `encounter`. Generate UUIDs when creating a **fresh synthetic source**, not by scanning or modifying existing patient data.
- The minimal legacy-compatible record fields read by the adapter: `patients(id,name,age,gender)`, `users(id,role)`, and `visits(id,patient_id,timestamp,status,systolic_bp,diastolic_bp,heart_rate,nihss_score)`.

The new source fixture generator defines this contract without importing legacy schema initialization. Source IDs/record UUIDs must never be reused for a different source/person/encounter. A recycled native primary key with a new UUID cannot inherit an earlier link: the boundary checks the catalog UUID on reads. Missing/mismatched markers, catalog identities or encounter ownership fail closed. Source reads use URI `mode=ro`, `query_only=ON` and a read transaction; no schema/record writes occur through the clinical boundary. As with any database, a privileged source owner can maliciously rewrite data while preserving its identifiers; this is not protection against a compromised DB administrator.

An authorized **local operator**, independently verifying the identity and record/assignment authorization, performs these explicit steps:

1. Register the precise source UUID, clinical role and numeric native primary key. The record must exist and its catalog UUID/clinical classification must match. Legacy `physician` classification is accepted only as canonical `doctor`; no username lookup is used. Register each encounter with its exact native visit ID and approved patient UUID; its existing native patient relation must match.
2. Link the approved clinical person UUID to an exact authority issuer/subject/role. The target person supplies a live bearer session for online verification. The response must match the **operator's explicit expected subject and role**. No name, email, patient code or username can substitute for an ID or proof.
3. For a doctor/technician, separately approve each encounter assignment, referencing the **mapping ID**, encounter UUID and the same staff member's live proof. A staff link alone grants no encounter access.

There is at most one active link for an authority subject and at most one active link for a clinical person. Duplicate requests and conflicting targets return 409, rather than overwrite/relink or silently claim idempotency. These invariants are backed by partial unique indexes and `BEGIN IMMEDIATE`, including concurrent linking. Registered native records and assignments are unique within their scopes.

Every person/encounter registration, link, assignment and revocation writes an operator/change reference, bounded reason, UTC timestamp, action and object UUID into the local audit in the **same SQLite transaction**. An audit failure rolls back the mutation. No raw token, password, email or patient payload is an audit field. The operator must use approval references, not paste secrets or patient details into free text. This is application-level mutation audit, not tamper-proof archival or a clinical-read audit system.

Operator commands are not HTTP routes. An admin bearer role cannot create a link, choose itself as a patient, or bypass clinical assignment. Trusting the local operator means OS/database custody plus independent hospital verification; the program cannot prove that a human chose the correct record. There is no self-service account claim, automatic import, email/code match, or automatic appointment-to-encounter assignment.

## Versioned contracts and live identity proof

Formal closed JSON Schemas live in `clinical_api/contracts/` for person/encounter registration, link creation, mapping receipts and assignment commands. `schemaVersion` must be integer 1; unknown fields, old/unknown versions, noncanonical UUIDs, invalid subjects, booleans as numeric IDs and role mismatches are rejected. Receipt/mapping IDs are durable UUIDs; revocation retains all history. The SQLite mapping store separately pins schema version 1 and its source UUID.

A distinct authority endpoint, **`POST /api/v1/identity/clinical-introspect`**, accepts an empty object and the caller's bearer token. Its closed response schema is `booking-backend/contracts/clinical-introspection-v1.schema.json`:

`{active:true,schemaVersion:1,issuer,subject,role,sessionId,expiresAt,roleVersion}`

The existing 2A `/introspect` and `/me` contracts are unchanged. `roleVersion` is a persisted clinical-role generation: staff role changes and revocation increment it atomically with session invalidation. Password change/recovery, login and logout do **not** increment it. Thus approved linkage survives ordinary session renewal, but a doctor → technician → doctor cycle cannot revive stale clinical permissions. Existing MongoDB rows are not backfilled; a missing generation reads as zero until an explicit authority role operation. Verification touches synthetic authority rows only.

The Python `IdentityAdapter`:

- Posts to an explicitly configured canonical loopback authority URL on **every protected request**, without success caching, shared signing key or fallback to Streamlit.
- Requires a successful HTTP 200, JSON content type, bounded declared body length, strict JSON (no duplicate keys/nonfinite numbers), exact fields/version/issuer/canonical role, canonical subject/session UUID, integer unexpired bounded expiry and nonnegative role generation.
- Structurally reads the unverified JWT payload **only to bind** subject/session/expiry/issuer/audience to the online response. This parsing never authenticates; the authority verifies signature and current session. Caller-provided roles/principals/URLs are never accepted.
- Disables HTTP proxies and redirects so environment proxy settings or a redirect cannot forward credentials elsewhere. HTTPS uses default certificate verification; plain HTTP is restricted to explicit loopback for this local synthetic milestone.
- Uses a bounded 0.05–5 second socket timeout (default 2 seconds), a 4096-byte response limit and no retries. This is a socket timeout, not a proven absolute wall-clock deadline against a malicious streaming peer.
- Maps invalid/revoked/expired authority sessions to 401; malformed/nonmatching responses, transport failures, timeouts, redirects and authority errors to 503. No response/token contents enter error messages or application access logs. A later healthy request revalidates normally; there is no permanent failure latch or cached allow.

Production remote authority addresses, TLS/service identity, distributed resilience policies and deployment hardening are not implemented. The local URL is configured by the operator, never by an HTTP caller. A forged/correctly shaped local fake response is used only in adapter protocol tests, not as evidence of signature validation; actual signature/session tests run against Node/MongoDB.

## New read-only access paths

The new API factory is `clinical_api.app.ClinicalApplication`. The local runner is `python3 -m clinical_api`, bound to `127.0.0.1:8010`. It uses the standard-library WSGI reference server for local verification, not a production server. No inference, upload, clinical write, suggestion-generation, treatment execution or browser integration is introduced.

| Path | Patient | Doctor / technician | Admin |
| --- | --- | --- | --- |
| `GET /api/v1/clinical/patients/:uuid` | Own linked clinical patient only | Denied; use assigned encounter path | Denied |
| `GET /api/v1/clinical/patients/:uuid/encounters` | Own registered encounter IDs only, capped at 100 | Denied | Denied |
| `GET /api/v1/clinical/encounters/:uuid` | Encounter belongs to own linked patient | Active encounter-specific assignment to own active link and current role generation | Denied |
| `GET /health` | Local source/mapping metadata readiness only | Same | Same |

Missing link/current generation is 403. A different patient's or unassigned encounter identifier returns 404, matching a missing record. Missing/invalid bearer session is 401; no query parameter can change subject or target ownership. Non-GET methods return 405; there is no HTTP mapping-management route. No cookie or role header grants access. All responses are JSON with `Cache-Control: no-store` and `nosniff`.

Encounter responses expose only timestamp, workflow status and the small stored-vitals/NIHSS field subset. They exclude scan paths, credentials, native IDs, predictions and treatment text. They carry `experimental:true` and `clinicianReviewRequired:true`. No calculation/model is invoked; an existing score is not validated clinical advice. Patient self-view exposes only name/age/gender for that approved record.

Link revocation removes access on the next request without deleting source data/history. Assignment revocation removes just that encounter permission. Re-linking creates a **new mapping ID**, so old assignments are not inherited. A role-generation change requires explicit unlink/relink and fresh assignment approval, even if the role later returns to its former value. A clinician's legacy username or `doctor_username` field never creates an assignment.

Authorization is a read snapshot. Requests already introspected/authorized before authority/link revocation may finish; there is no distributed MongoDB/SQLite transaction or retroactive cancellation of in-flight reads. New requests always revalidate. Clinical data writes are deliberately outside this milestone.

## Configuration and operator use

There are no default DB paths, `.env` discovery, implicit migration or automatic mapping-store initialization in Python. Set these explicitly for a **fresh private synthetic fixture**:

```text
CLINICAL_DATA_MODE=synthetic
CLINICAL_RECORDS_DB=/absolute/private/path/new-synthetic-records.sqlite
CLINICAL_LINKS_DB=/absolute/private/path/new-clinical-links.sqlite
CLINICAL_SOURCE_ID=<new source UUID matching the fixture marker>
IDENTITY_INTROSPECTION_URL=http://127.0.0.1:3000/api/v1/identity/clinical-introspect
```

The source and linkage paths must be distinct. Missing/unmarked stores fail closed and are never created by reads. Do not put real keys/tokens in tracked configuration. Python does not need the JWT signing/delivery key. A controlled fresh synthetic source may be generated explicitly with `clinical_api.tests.fixtures.create_records`; no existing database is an input.

Run `python3 -m clinical_api.operator init` once for the new linkage file. It refuses an existing file. The operator is prompted for a reference and independent approval reference; no real patient names/details should appear in reasons. Further actions are `register_person`, `register_encounter`, `link`, `assign`, `revoke_link`, `revoke_assignment`. Versioned command fields are defined in the schemas. A revoke command is exactly `{schemaVersion:1,id:<mapping-or-assignment-UUID>}`.

Link/assign request the target person's token using hidden `getpass` input and require an interactive private terminal; tokens are not accepted through arguments, JSON commands, logs or insecure input fallback. Outputs are ID-only receipts. There is no bearer-based HTTP management privilege. The CLI is for a hospital-authorized local operator; direct SQLite write access is inherently privileged. No real operator approval, actual patient linkage or manual terminal handoff was performed for this verification; integration tests call the same operator services with synthetic approvals/proofs.

## Reproduce verification

From the stroke repository root:

```sh
bash scripts/test-clinical-bridge.sh
```

The helper uses a unique private Docker network, tmpfs MongoDB (no host port) and a disposable Node/Python test container with `/tmp` on tmpfs. It runs locked npm installation/build, all booking/identity regressions, new Python HTTP/integration tests, legacy Python guard tests and syntax compilation. Python is installed only in that disposable container; no ML/runtime dependency is added to the legacy requirements. Fixture credentials travel only over a private child-process pipe and loopback; keys remain in Node. No fixture file or credential report is written to Git/the host. Only owned containers/network are removed, with no volume deletion/pruning.

See [Milestone 2B verification](hospital-milestone-2b-verification.md) for executed counts, failures fixed and limitations. Existing production-style clinical schema, Streamlit browser behavior, real hospital workflows, read-audit/retention, MFA, TLS/service authentication, and a unified portal remain unverified/future work. Clinical predictions/treatment suggestions remain experimental and subject to clinician review.

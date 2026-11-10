# Appointment and assessment workflow v1 — Milestone 3

## Scope

The booking backend now connects to the isolated Python clinical API over an explicit local HTTP boundary. A confirmed appointment can open one synthetic assessment encounter, with immutable UUID references, explicit approved patient/doctor mappings and durable idempotency. Doctors/technicians can also open an unscheduled emergency encounter under a separately approved patient-scoped intake grant.

No Streamlit session, existing patient database, scan, clinical model or hosted AI client is used. An encounter is an **`ASSESSMENT_PENDING` record**, not a prediction, completed assessment, diagnosis or treatment instruction. Read responses remain experimental and require clinician review.

MongoDB scheduling and SQLite clinical storage remain separate services. The source registry SQLite is read-only; new records live in the Python service's explicitly initialized **clinical store v2**, alongside its linkage, assignment, receipt and audit tables. This is not a write to the historical `visits` table or an implicit migration of an existing source.

## Explicit configuration and storage

- Booking: `CLINICAL_API_URL=http://127.0.0.1:8010/api/v1/clinical/assessment-requests`, explicitly set. An unset/nonlocal/noncanonical URL fails before any appointment reservation. Redirects are rejected; HTTP calls have a two-second overall fetch deadline and a 4096-byte bounded receipt. No network call is held inside a MongoDB transaction.
- Python: existing explicit synthetic source/linkage configuration from [clinical linkage v1](clinical-linkage-v1.md), plus **`CLINICAL_STORE_VERSION=2`** for a fresh store. `python3 -m clinical_api.operator init` refuses an existing file. `schema.sql` (v1) is unchanged; new `schema-v2.sql` defines v2. There is no automatic upgrade, marker insertion, data copy or backfill. A v1 store remains readable with its v1 configuration and cannot create assessments.
- Source UUIDs and native record UUIDs stay immutable. New locally owned assessment encounters have `native_id=NULL` in the clinical encounter registry and a corresponding `assessment_records` row; they never masquerade as an original source visit.
- New bookings receive `appointmentUuid` only when written. There is no Mongoose default that invents a UUID when hydrating an old row. Historical appointments without one require a separately approved adoption procedure; the new API does not silently convert Mongo IDs.

The local WSGI reference server now handles independent requests in threads, using per-operation SQLite connections/transactions. It remains a loopback synthetic prototype, not a production server or concurrency/capacity claim. Existing source/reference requirements and npm dependency lock are unchanged.

## Versioned contracts

Closed JSON Schemas:

| Contract | Location |
| --- | --- |
| Appointment DTO | `booking-backend/contracts/appointment-v1.schema.json` |
| Scheduled intent | `booking-backend/contracts/assessment-intent-v1.schema.json` |
| Durable workflow state | `booking-backend/contracts/assessment-state-v1.schema.json` |
| Live appointment proof | `booking-backend/contracts/appointment-proof-v1.schema.json` |
| Clinical scheduled command | `clinical_api/contracts/scheduled-assessment-v1.schema.json` |
| Immutable clinical receipt | `clinical_api/contracts/assessment-receipt-v1.schema.json` |
| Emergency command | `clinical_api/contracts/emergency-assessment-v1.schema.json` |
| Patient intake approval | `clinical_api/contracts/intake-grant-v1.schema.json` |

All public appointment, request, encounter, mapping, grant and source references are canonical UUIDs. Authority subjects retain their explicitly scoped Mongo ObjectIds. The existing availability identifier remains a Mongo ID; it is not a clinical reference. No name/email/patient code/username matching is introduced. Client-supplied patient/doctor subjects, roles, outcome states and encounter IDs are not accepted by the booking intent route.

The immutable scheduled command hash is SHA-256 of compact UTF-8 JSON for this ordered array:

`[1,"SCHEDULED",requestId,appointmentId,encounterId,sourceId,patientId,patientMappingId,clinicianMappingId]`

These fields are ASCII UUIDs/constants; Node and Python produce the same compact array bytes. An intent hash excludes the server-allocated encounter UUID and mode, and includes the appointment/request IDs and explicit clinical references. Reusing a key with different content or ownership is 409. Emergency request hashes use a separate `EMERGENCY` domain and include patient/actor mapping, intake grant and reason code; their encounter UUID is stable UUIDv5 under the source namespace. A client must use a new random request UUID for a genuinely different operation.

## Booking API

Canonical paths are below. Existing `/api/appointments` routes stay compatible and enforce the same cancellation reservation guard.

| Method/path | Authorization and behavior |
| --- | --- |
| `POST /api/v1/appointments` | Patient only. `{schemaVersion:1,availabilityId,notes?}`. Same transactional slot claiming and uniqueness as before; 201 + Location + UUID DTO |
| `GET /api/v1/appointments/:uuid` | Owning patient/assigned doctor only. 404 for another owner's appointment, 403 for admin/technician |
| `PATCH /api/v1/appointments/:uuid/cancel` | Owning patient/assigned doctor, `{schemaVersion:1}`. No active assessment reservation; cancellation/slot release remain atomic in MongoDB |
| `POST /api/v1/appointments/:uuid/assessment-requests` | **Assigned doctor only**, fresh live session/current role generation. `{schemaVersion:1,requestId,sourceId,patientId,patientMappingId,clinicianMappingId}` |
| `POST /api/v1/appointments/:uuid/assessment-proof` | Same assigned doctor, `{schemaVersion:1,requestId}`; internal online proof for the clinical boundary, not a clinical data endpoint |

An intent must reference the exact approved clinical patient and clinician mapping IDs. Node takes the patient/assigned doctor from the actual confirmed appointment. A patient, admin, technician or unrelated doctor cannot reserve a scheduled assessment. Technicians may receive ordinary encounter read assignments and may create emergency encounters under intake grants; they are not implicitly the appointment's doctor.

The proof endpoint verifies a live session, the durable active request, confirmed appointment, assigned active doctor, active patient identity, original actor/current role generation and appointment reservation. It binds request/encounter/command hash and caller session; a proof lasts at most 60 seconds. Python fetches it online from the **configured authority origin**, checks its exact closed contract and compares actor/session/command identity. A proof or actor field supplied in a clinical request body is never trusted.

Responses from assessment intent creation:

| HTTP/state | Meaning and next action |
| --- | --- |
| 200 `CREATED` | SQLite receipt acknowledged and Mongo workflow finalized; record exists, clinical assessment still pending |
| 202 `PENDING` + Retry-After | Outcome not known/another delivery active; retry the **same UUID/body** with a valid current session |
| 422 `REJECTED` | Immutable SQLite rejection receipt; no encounter was created for that request. Correct the issue and use a new request UUID |
| 400 | Invalid fields/version/UUID; no new intent accepted |
| 401 / 403 / 404 | Invalid session, forbidden actor or inaccessible appointment |
| 409 | Nonconfirmed appointment, active competing intent, key conflict or cancellation requiring review |
| 503 `assessment_state_unavailable_retry_same_request` | Local acknowledgement persistence failed; preserve request ID and retry, rather than assume clinical failure |

Semantic v1 errors include `schemaVersion:1` and an error string. Identity/auth errors retain their existing authentication semantics. No raw exception, clinical payload or token is an error message. GET/intent responses use no-store caching. Versioned bookings retain the existing booking rate limiter.

## Reliability protocol and cancellation policy

| Phase | Durable state and boundary |
| --- | --- |
| Reserve | One MongoDB transaction writes a `PENDING` request, command/intent hashes, fixed encounter UUID and the appointment reservation. Actor/patient/status/ownership checks serialize with relevant identity and appointment mutations |
| Deliver | A four-second leased attempt performs at most one bounded clinical HTTP POST. Retries need a new authenticated call; **bearer tokens are never persisted**, and no background sender is introduced |
| Validate | Python validates live identity and a live Node appointment proof, explicit source/patient/clinician mappings, role generations and stable source UUIDs |
| Commit clinical outcome | One SQLite transaction commits encounter registry + assessment record + explicit clinician assignment + immutable request receipt + mutation audit; or a durable `REJECTED` receipt with no encounter |
| Acknowledge | A fenced MongoDB transaction records `CREATED`, or records durable `REJECTED` and releases the reservation. A stale lease cannot overwrite a newer final state |

MongoDB has one blocking request per appointment; SQLite has one created receipt/record per appointment and one receipt per request ID/hash. Replays return the persisted outcome without creating another record or assignment. No at-rest bearer token, cross-database transaction, distributed exactly-once guarantee or time-based business-lock expiry is claimed.

**Cancellation is deliberately conservative.** Before reservation, cancellation may win and creation is rejected. If reservation wins, ordinary cancellation returns 409 while `PENDING` **and after `CREATED`**. A local lease expiring only permits a resend; it does not unlock cancellation. A transport error, HTTP error, timeout, bad receipt or Mongo acknowledgement failure never releases the reservation. Only an immutable, validated SQLite rejection receipt can do so. Rejected requests cannot later turn into creations under the same key.

Thus, a clinical commit followed by a lost response cannot be followed by an ordinary cancellation that wrongly assumes no record exists. Records and audit history are never deleted to repair a scheduling outcome. Once assessment intake has started, cancellation/reassignment/closing care needs a separate reviewed workflow, not deletion of the clinical record. An unresolved request with a permanently revoked clinician/mapping may require operator review; there is no unsafe force-abort/unlock endpoint.

Each retry authenticates again. Normal logout/password/session renewal can recover with a fresh session for the same doctor and role generation. A role-generation change does not silently reauthorize the old intent. A created receipt can reconcile existing metadata even if old clinical mappings have since been revoked; clinical data reads still require current links/assignments. In-flight operations already authorized may finish; revocation is not a distributed rollback.

## Unscheduled emergency assessment

`POST /api/v1/clinical/emergency-assessments` does not need an appointment or appointment proof. It requires a live mapped doctor/technician, exact approved patient mapping, source UUID and an unexpired patient-scoped intake grant:

`{schemaVersion:1,requestId,sourceId,patientId,patientMappingId,actorMappingId,intakeGrantId,reasonCode}`

`reasonCode` is `SUSPECTED_STROKE` or `URGENT_REASSESSMENT`, a routing label rather than an inferred diagnosis. A local authorized operator issues `grant_intake` using the existing private-terminal proof procedure, exact mapping/patient UUID and `expiresAt` between 60 seconds and 24 hours in the future. The grant is audited and can be revoked with `revoke_intake` and `{schemaVersion:1,id}`. There is no admin HTTP shortcut, role-only blanket grant, default credential or unknown-patient auto-link.

The same local SQLite transaction creates a stable encounter/receipt and an assignment to the approved creating staff link. Grant expiry/revocation prevents **new** intake; it does not delete an existing encounter or replace its separately revocable read assignment. Replays of an existing authorized request return its receipt without new intake. Conflicting command/key reuse is 409. An active current clinical link remains required for emergency replay.

This is a synthetic, known-patient workflow. It is not an offline break-glass system or a real emergency-care service: missing linkage/grants or an unavailable identity authority fails closed. Unknown/unidentified-patient intake and real emergency operational procedures remain future work; the application must not be represented as a substitute for them.

## Clinical-read audit

Supported patient and encounter GET handlers audit **allowed, denied and recognized failed** access decisions before disclosing data. The existing local audit table stores action `CLINICAL_READ`, UTC time, authority subject (or `unauthenticated`), canonical resource UUID (or `invalid`) and a bounded JSON reason with version, session ID, role, resource kind, outcome, status and fixed error code. It stores no token, password, email, demographic/vital payload, request URL or free clinical text.

A read and its audit use a local write transaction for the authorization snapshot/audit, with separate read-only source access. If audit/store persistence fails, return 503 **without the clinical response payload**. Existing v1 and new v2 stores support this audit; no v1 schema migration is needed. Only the sidecar audit history changes during reads; source databases remain read-only. Invalid routing/method/body requests rejected before a clinical read handler are not clinical-read audit events.

Audit rows are local application history, not tamper-proof archival, a byte-level delivery receipt or a compliance certification. Local DB/OS administrators remain privileged. Retention, export, encryption/key custody and operational audit-review tooling need a separate production design.

## Verification and remaining work

Run `bash scripts/test-clinical-bridge.sh` for locked build, all Node regressions, Python protocol/identity/workflow integration tests, old Python guards and syntax checks. Both runners use a shared Git-local `flock` lock to prevent overlapping dependency builds. The same private tmpfs fixture rules remain: no host ports, no normal data/volumes, no provider/model calls. See [Milestone 3 results](hospital-milestone-3-verification.md) for actual counts and fault distinctions.

There is no shared portal, Streamlit integration, inference, clinical editing/finalization, appointment rescheduling/care cancellation workflow, automatic background reconciliation or actual-data migration. Prototype loopback transport/reference serving, test dependency bootstrapping, authorization snapshots and SQLite write serialization are not production TLS/service identity, throughput, uptime or clinical-safety claims.

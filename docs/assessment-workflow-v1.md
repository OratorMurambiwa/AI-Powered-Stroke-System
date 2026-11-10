# Synthetic assessment workflow v1 (Milestone 4A)

This API records **human observations and clinician review**, not stroke classification, treatment eligibility or clinical decision support. `experimental=true`, `inferencePerformed=false` and `clinicianReviewRequired=true` are explicit response fields. No legacy ML, treatment, Streamlit authentication or hosted service is imported or invoked.

## Explicit storage boundary

Set `CLINICAL_DATA_MODE=synthetic` and `CLINICAL_STORE_VERSION=3` with explicit separate synthetic source/clinical-store paths and source UUID. The local operator initializes a **new** `LinkStore(path, source_id, 3)`; initialization uses exclusive file creation with mode 0600. Startup never initializes, migrates or adopts an existing store. v1/v2 schemas remain unchanged and retain their earlier endpoints; new workflow paths exist only for v3. Existing v2 encounter records are not automatically copied or upgraded. Create scheduled or emergency encounters using the existing intake contracts in the fresh v3 fixture/store, then use their stable encounter UUIDs.

MongoDB scheduling remains separate. Intake reservations, proof, retries and cancellation rules from [appointment/encounter v1](appointment-encounters-v1.md) still apply. An assessment approval is not booking completion or discharge.

Scan bytes, hashes, metadata, workflow state, immutable action receipts and input snapshots live together in the private SQLite clinical store. There is no client-supplied path, filename, upload directory, static scan URL or filesystem/object-store dual write. Database access/backup custody is privileged local operator work. Do not expose the database file, journal, backups or source paths through a web server. This prototype does not provide encryption at rest or tamper-proof archival retention.

## Endpoints and authorization

All paths are under `/api/v1/clinical/encounters/{encounterId}`:

| Method/path | Access |
| --- | --- |
| `GET /assessment` | Currently assigned doctor/technician: observations, internal notes and versioned history. Owning patient: only an APPROVED projection, without internal notes/history. |
| `POST /assessment` | Currently assigned doctor/technician: OBSERVATIONS, SCAN, SUBMIT. Assigned doctor only: NOTE, APPROVE, REJECT. |
| `GET /scans/{scanId}` | Assigned staff, or owning patient only after approval. Scan must belong to this exact encounter. |

Every access uses live booking introspection, current role generation, exact clinical link and active encounter assignment (or patient ownership). Admin role grants no clinical access. Replay does not bypass these checks. Staff-to-patient mapping is not inferred from name, email or patient code. Assignment/revocation uses the existing audited operator workflow; emergency intake still needs the existing patient-scoped grant.

Workflow endpoints accept only encounters created by the scheduled/emergency intake service, not historical source visits. In v3, patient reads through the older generic encounter endpoint return `LEGACY_RESULT_UNAVAILABLE` for source visits; they do not bypass approval by exposing legacy vital/NIHSS fields. Generic new-encounter reads expose intake metadata only.

## Actions and versioning

See [action contract](../clinical_api/contracts/assessment-action-v1.schema.json), [receipt](../clinical_api/contracts/assessment-action-receipt-v1.schema.json) and [view](../clinical_api/contracts/assessment-view-v1.schema.json). JSON rejects duplicate/unknown keys, non-finite values, unversioned objects and noncanonical UUIDs. An action has exactly:

```json
{"schemaVersion":1,"requestId":"00000000-0000-4000-8000-000000000001","expectedVersion":0,"action":"SUBMIT","data":{}}
```

This example illustrates shape only; submitting an empty assessment fails. New encounters start at workflow version 0/DRAFT. SQLite `BEGIN IMMEDIATE` serializes mutations. Compare the expected revision inside the write transaction; stale revisions return 409. At most 128 actions and 16 scans/16 doctor notes per encounter bound storage/read history. These are prototype limits, not clinical policies.

- **OBSERVATIONS** replaces the full vitals/NIHSS set atomically. Units are explicit in field names. All six vitals and all 15 NIHSS components are required. Numeric acquisition bounds prevent malformed input; they are **not** normal ranges, diagnostic thresholds or eligibility criteria. NIHSS scores must be integers within the component ranges. Require an explicit UTC observation timestamp no later than receipt. No stroke class, NIHSS interpretation or treatment suggestion is computed.
- **SCAN** takes only `mediaType=image/png` and strict `contentBase64`. No path/name/URL is accepted. A successful receipt contains a server-generated scan UUID.
- **NOTE** appends a bounded, attributed doctor-only internal note. Notes are never included in patient projections.
- **SUBMIT** requires recorded vitals, NIHSS and at least one scan. DRAFT/REJECTED becomes SUBMITTED. Inputs and notes cannot change while submitted.
- **APPROVE/REJECT** requires an assigned doctor, SUBMITTED state, bounded explicit summary/rejection explanation and `attested=true`. Both decisions append provenance and freeze that reviewed version. Rejection remains invisible to patients and permits corrections/resubmission. Approval is final and immutable in this milestone. No reopen, silent amendment or replacement of an approved result is provided.

Identical UUID/body/actor/encounter retries return the immutable receipt, including after a lost acknowledgement. Different bodies, actors or encounter targets using that UUID return 409. Replays are still subject to current authentication/assignment. New requests against a frozen or stale version fail. A rejected action does not consume its request ID or version. This is action idempotency, not content-hash deduplication; a new scan request ID can upload the same valid pixels again, within the encounter limit.

## Scan validation and delivery

JSON bodies have a 1,400,000-byte ceiling, scan content a 1 MiB ceiling. Intake retains its 8192-byte limit. Only a deliberately narrow PNG subset is supported: valid signature, chunk bounds/order, CRCs, IHDR/contiguous IDAT/IEND, no trailing bytes, 8-bit grayscale/RGB, 1–1024 pixels per axis, no interlace. Bounded zlib decompression must yield exactly the expected raster size with valid PNG filter bytes. Metadata, animation, palette/alpha, ancillary chunks, external references, SVG/PDF/DICOM/JPEG, invalid compression and polyglot tails are rejected. This is a synthetic image container check; it does not establish medical image quality, diagnostic suitability or malware-free status for every conceivable decoder. DICOM handling, clinical imaging fidelity, de-identification and an independently hardened decoder/scanner need a separate milestone.

Reads verify stored byte length and SHA-256 before returning `image/png`, `Content-Disposition: attachment` with a server UUID, `Cache-Control: no-store`, `nosniff` and a restrictive sandbox CSP. No inline HTML or client filename is rendered. A scan lookup includes both encounter UUID and scan UUID. No unauthenticated/static delivery exists.

## Audits, provenance and failure behavior

Each accepted action commits its input snapshot, current link/role/session provenance, action timestamp, request hash, response receipt and mutation audit in the same transaction as observations/scan/state. This includes the human reviewer and explicit summary for the reviewed version. Raw scan data stays in the scan table; immutable snapshots contain scan IDs/hash/size only.

Parsed workflow accesses and downloads commit allow/deny/failure audits before disclosure, without tokens, passwords, vital values, note/summary text or scan bytes in the audit table. Clinical input history is private clinical data, distinct from audit metadata. Mutation validation failures roll back their savepoint, then commit a denial audit; database or audit failure rolls back everything and returns 503. A failed read audit returns no scan/result bytes. Malformed HTTP envelopes and invalid scan identifiers can be rejected before authorization/audit; there is no separate ingress security logging service in this milestone.

Typical responses: 400 invalid action/content/observations; 401 invalid session; 403 forbidden clinical role or doctor-only decision; 404 unavailable/unowned/unassigned/unapproved record; 409 stale revision, conflict, frozen state or quota; 413 oversized body/scan; 415 unsupported HTTP media type; 503 unavailable identity/source/storage/audit or scan integrity failure. Unknown failures return a generic 500 without internals. Restored dependencies permit an authenticated retry of the same command. Revocation affects subsequent validations; already authorized in-flight operations may finish.

The local threaded WSGI server remains a prototype: production request deadlines, TLS/service identity, distributed throttling, database encryption/backup/retention, imaging validation and clinical governance remain unimplemented. No shared frontend, notifications, inference, hosted AI or legacy login integration is included.

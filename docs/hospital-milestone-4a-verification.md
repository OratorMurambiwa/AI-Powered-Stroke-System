# Milestone 4A verification — 2026-11-10

Baseline: `f5ae4c7cba37c114bf9e20768f9d5e5474108dea`. Scope: synthetic human assessment observations, private PNG uploads/downloads, assigned-doctor notes/review, approved patient projections and transactional revision/history/audits. See [workflow v1](assessment-workflow-v1.md) for contracts, endpoint paths, input bounds and operational limits.

## Executed results

| Check | Verified result |
| --- | --- |
| `bash scripts/test-clinical-bridge.sh` | Final serial run exited **0**, private tmpfs MongoDB replica set and disposable Node/Python test container; no host ports or persistent database volumes |
| Node booking/identity regressions | **44 TAP tests passed**, zero failures/skips (42 child scenarios plus 2 parent tests) |
| Python clinical suite | **83 passed**: 18 protocol/config/operator cases, 16 earlier real linkage cases, 23 Milestone 3 workflow cases and **26 new 4A integration cases** |
| Legacy Python registration/default-user guards | **4 passed**, unchanged |
| Total Python | **87 passed**, including **65 actual cross-language integration cases**; no skipped cases |
| Build/static checks | Strict TypeScript build via npm test; Python compilation; shell syntax; all contract JSON parsed; `git diff --check` passed |
| Dependencies | `npm ci` used the existing lock; `npm audit` reported **0 vulnerabilities**. No runtime dependency or lock changes |

An initial run stopped the new test fixture before tests: the existing safety allowlist correctly refused the newly named synthetic database. The explicit allowlist now includes that one new private database, preserving its exact-host/replica-set guard. The initial run is not counted as successful 4A evidence. The final run passed all suites. Host compilation initially encountered ignored bytecode caches owned by earlier containers; redirecting bytecode to a private `/tmp` cache passed, and the final Docker helper compiled with its existing private cache configuration.

Runtime matches Milestone 3: Node 22.14.0, npm 10.9.2, TypeScript 5.9.3, disposable Alpine Python 3.12.16/SQLite package 3.48.0-r4, MongoDB 8.0.17 at the existing pinned digest. Host shell/JSON/compile checks supplement the isolated runtime results; they are not deployment or real clinical validation.

## New integration evidence

The 26 cases exercise the actual compiled Express identity/booking authority through signed real sessions, MongoDB scheduling transactions and the actual threaded Python WSGI application with fresh marked synthetic sources and fresh v3 SQLite stores. Synthetic PNGs are generated from tiny test rasters, not copied from existing scans. Fixtures retain original source-byte hashes and verify no source modification after every case.

Verified:

- A confirmed booking creates a v3 encounter through the existing proof/receipt protocol. The assigned doctor records observations; an unassigned technician cannot. Cancellation remains blocked after intake. Separate emergency intake creates the remaining test encounters under exact patient-scoped grants, then the audited operator explicitly assigns the technician.
- Assigned technicians record all six unit-labeled vitals and 15 NIHSS components with UTC observation time, upload a structurally decoded PNG and submit. Invalid/bool/out-of-range/incomplete values and future timestamps leave the workflow version unchanged. No classification, severity interpretation, eligibility or treatment logic runs.
- Assigned doctors review submitted snapshots and explicitly attest approval or rejection. Technician notes/decisions are forbidden. Doctor notes are attributed and internal. Submission locks editing; rejection allows correction and explicit resubmission; approved results cannot be changed or rejected afterward.
- Patients see 404 before approval and for rejected work. The owning patient sees the approved immutable human summary, observations, time and scan metadata/bytes afterward, without internal notes/history. Other patients, admin, unlinked and unassigned staff cannot read/upload. Scan IDs cannot be used under another encounter. The older v3 patient encounter route cannot expose unapproved legacy vitals/NIHSS.
- Exact observation, upload and approval retries return immutable receipts without another version/blob/history entry. Changed body/actor conflicts. Four concurrent duplicate uploads produce one scan/revision. Competing distinct updates and competing approval/rejection decisions admit one expected revision and return 409 for the other.
- SVG/HTML, PDF, executable signatures, fake DICOM, invalid CRCs, truncation, trailing polyglot data, unsupported/zero/oversized dimensions, invalid filter bytes, metadata chunks, invalid base64, decompression bombs, >1 MiB content, client paths and filenames are rejected before any blob persists. The validator intentionally accepts only a restricted grayscale/RGB PNG subset, not general clinical imaging.
- Successful scan reads return exact synthetic bytes with attachment/no-store/nosniff/sandbox headers. Audit-write failure returns 503 without scan data. Corrupt stored bytes fail length/hash validation with 503.
- A test-only SQLite trigger aborts the scan mutation audit after blob insertion; blob/state/receipt/history all roll back. Removing the trigger permits the same request to succeed. Allowed/denied access audit metadata contains no vital payload, image base64, passwords or bearer tokens.
- Actual closed-loopback introspection transport and missing synthetic store files fail closed. Restoring them allows fresh authenticated work. Assignment/link revocation, stored session expiry and logout deny subsequent reads/writes/downloads and cannot be bypassed by idempotency replay. A new real login restores only still-authorized access.
- Fresh v3 initialization refuses an existing v2 file, and a version mismatch leaves its bytes unchanged. No schema v1/v2 migration is performed.

The old 16 linkage and 23 intake cases still run once each, not through duplicated inherited tests. Their helper methods were separated into a non-test fixture class for reuse. Earlier actual authority stop/resume, mapping drift/role epoch, receipt loss/malformed acknowledgement and scheduling cancellation/partial-failure cases remain covered. Fault distinctions from Milestone 3 still apply: SQLite trigger failures and deliberately altered HTTP responses are test injections, not claims of physical database/process failures.

## Preservation and review

Only source, contracts, tests and documentation change. The historical `data/` tree, original database records, credentials, uploads, model weights, notebook, legacy clinical source modules and dependency locks remain unchanged. No existing patient database or scan is opened as an input. No inference, hosted AI call, treatment decision or Streamlit session integration is performed. Tests use separate synthetic SQLite files and run-specific tmpfs MongoDB, never normal services/data. Cleanup removes only owned test containers/network, not persistent volumes. The original Hospital-booking-system repository is unchanged.

Staged paths/diff, ignored artifacts and credential/private-key patterns were reviewed before publication. No .env, database, image, weight, generated build, cache, raw token or runtime credential is staged. Git author remains the user's existing identity; publication uses a normal push with no AI coauthors.

## Remaining work and limits

- Synthetic-only API; no real clinical record adoption, unified frontend, DICOM/JPEG, clinical image fidelity/de-identification validation or inference. Original stroke classifications/treatment heuristics remain experimental and separate.
- v3 requires a fresh explicitly initialized store; existing v1/v2 stores/encounters are not silently upgraded/copied. Rehearsed, authorized migration/adoption is future work.
- Approval is immutable in this milestone. Add a separately reviewed amendment/reopen/care-completion and post-intake cancellation policy before real operations. There is no unknown-patient emergency break-glass policy.
- Numeric bounds and PNG structural/raster checks are input validation, not clinical correctness, a general malware verdict or medical safety evidence. Clinician attestation records a human decision; it does not validate diagnosis or treatment.
- Local SQLite storage, serialized audits and bounded WSGI requests remain a prototype, without production TLS/service identity, ingress deadlines/throttling, encryption/key custody, capacity evidence, audit export/retention or tamper-proof archival controls. File/journal/backup access is a privileged operational boundary.
- MongoDB and SQLite remain separate. Pending intake still uses authenticated on-demand retries, not distributed atomicity/background reconciliation. Revocation blocks subsequent validations; already authorized in-flight work may complete.

# Milestone 2B verification — 2026-11-09

Baseline: `071500cafb75693b490d8b8fb27613016c0e73bc`. Scope is explicit synthetic clinical identity linkage, a live Python authority adapter and new read-only ownership/assignment paths. Existing Streamlit, actual patient stores and clinical inference are outside this execution. See [clinical linkage v1](clinical-linkage-v1.md) for schemas, lifecycle rules and operator procedures.

## Executed checks

| Check | Verified result |
| --- | --- |
| `bash scripts/test-clinical-bridge.sh` | Exit 0: fresh private MongoDB replica set, disposable Node/Python container, locked npm install, TypeScript build, all regressions, Python integration/transport tests and syntax compilation |
| Node booking/identity suite | **44 TAP tests passed**, zero failures/skips, including two parent tests. **42 child scenarios**: all 40 milestone-2A regressions plus two new clinical-proof/role-generation scenarios |
| Python clinical suite | **30 tests passed**: **16 real cross-language HTTP/MongoDB/SQLite integration cases**, plus **14 protocol/configuration/operator-boundary tests** |
| Existing Python registration guard suite | **4 tests passed**, unchanged |
| Total Python tests | **34 passed**, zero failures/skips |
| Full dependency audit | `npm audit`: **0 reported vulnerabilities**; unchanged npm lockfile, no application dependency addition/upgrade |
| Python syntax | `compileall` for `clinical_api`, `app.py`, `core`, `models`, `pages`, `services` passed inside the test container; no clinical runtime import/inference |
| Shell/static review | Test helper shell syntax and `git diff --check` passed; no legacy authentication/ML imports in the new Python package |

A shell failure-control probe also verified that npm install/test/audit errors stop the helper before Python checks. The first cross-language run failed during **new synthetic fixture setup** because its visit INSERT had one extra SQL placeholder. It did not exercise clinical access or touch existing data. The fixture was corrected and the complete suite rerun. Subsequent source-UUID and private-terminal protections were included in the final passing run. Generated Python bytecode is redirected to the test container's private `/tmp` cache, avoiding host root-owned cache artifacts in later syntax checks.

## Real integration evidence (16 cases)

The Python tests start the actual compiled Node authority as a child process, using a separate private MongoDB database. New synthetic identities are fixture-provisioned, then obtain sessions through real HTTP login. Signing/delivery keys are generated inside Node and never sent to Python. Synthetic credentials/proofs travel only in a private child-process pipe and loopback HTTP; they are not written to host fixtures, reports or Git.

Each integration case creates **two fresh SQLite files**: a marked synthetic clinical source with legacy-compatible minimal tables and immutable source/record UUID catalog; and an independent versioned linkage/audit store. Python's clinical HTTP server is exercised over a real local socket. Link/assignment operations call the same local operator services used by the CLI, using explicit synthetic approval references and live target proofs.

Verified behaviors:

- Patient linkage resolves exactly the approved clinical UUID. Patient A cannot view Patient B or B's encounters; own encounter enumeration excludes B. Native integers/codes are not accepted as API patient identifiers.
- Doctors and technicians require both an active link and an encounter-specific assignment. They cannot read an unassigned encounter, another encounter of the same patient, or the patient-wide self-view route. Admin, unmapped patient, unmapped doctor and unmapped technician sessions receive no clinical access.
- Duplicate/conflicting subject/person links and duplicate assignments return conflicts; concurrent link attempts produce exactly one success and one conflict. Wrong target proof, mismatched role, source ID, encounter/patient relationship, missing record, unknown version and email/code input fields are rejected.
- Assignment revocation removes access. Link revocation removes access while preserving records/history. Re-linking yields a new mapping ID and does not inherit old assignments; explicit reassignment restores access.
- Persistent UUIDs and mappings survive store reopening. Source marker mismatch, wrong store/source version and **native primary-key reuse with a different record UUID** fail closed. Restoring the correct generated fixture restores access.
- The real authority HTTP listener is stopped and restarted through a private fixture process pipe. Clinical reads and link creation return 503 during the outage; a subsequent healthy request succeeds without cached authorization or re-linking. Missing source/mapping files similarly return 503, are not recreated by reads, and recover after restoration.
- An injected SQLite audit trigger failure rolls back mapping/assignment insertion. Removing the trigger permits a successful approved operation, with no partial grants left behind. This is a test-only injected storage fault, not an actual disk-failure claim.
- Real authority staff role changes doctor → technician → doctor invalidate sessions and advance role generation. A new doctor session still cannot use the old mapping; explicit re-link plus fresh assignment is required. Authority revocation, expired stored session and logout deny clinical access. A fresh patient login restores access through the existing approved patient link.
- Source bytes are hashed before/after each case and remain unchanged. The primary-key-reuse fault deliberately edits only its newly generated source fixture, then restores its original bytes. No actual scan/treatment field is read/exposed; returned encounter data is marked experimental/clinician-review required.

## Protocol/configuration tests (14 cases)

These use a controlled local HTTP stub **for malformed/error responses**, not as evidence of real JWT signature validation. They cover strict JSON/type/version/field checks, duplicate keys/nonfinite values, oversized/deeply nested or non-JSON responses, wrong identity/session binding, expired/overlong proof, unknown canonical role, invalid session statuses, HTTP failures, redirects without bearer forwarding, disabled environment proxies, socket timeout and recovery. They also verify no implicit `.env`/patient DB configuration, no creation of missing stores during reads, rejection of unmarked sources/aliased stores, and refusal to prompt for a target token without a private interactive terminal.

Actual hidden-terminal human approval is not performed here; the operator services and private-terminal guard are tested. The authority's legacy 2A operator CLI remains covered by the Node regression suite.

## Environment and preservation

The helper uses Node **22.14.0**, npm **10.9.2**, TypeScript **5.9.3**, the existing locked Mongoose/Express/JWT dependencies, and Python **3.12.16** installed into the disposable Alpine 3.21 test container. SQLite library package resolved to **3.48.0-r4**. No Python third-party library, ML dependency or model was installed for this boundary. The APK index/package snapshot is not a portable application dependency lock; reproduction may resolve a later compatible Python 3.12 package. Legacy Python application requirements and npm lockfile are unchanged.

MongoDB **8.0.17** uses the same pinned image digest as earlier milestones. A run-specific private Docker network has no host-published database/API port. MongoDB database/config directories and the test container `/tmp` use tmpfs. The helper removes only its own containers/network, without pruning or volume deletion. Normal Compose services and reserved host ports are untouched.

The source Hospital-booking-system repository remains unchanged. The isolated stroke checkout receives source/tests/contracts/docs only; no existing `data/` Git entry, patient store, uploaded scan, credentials, weight or notebook changes. No automatic identity matching, original SQLite/MongoDB query, source migration, password rotation, Streamlit integration or hosted AI request was executed. New runtime source/mapping DB files exist only in private synthetic fixtures and are not tracked.

## Remaining work and limits

- These are **synthetic-only** new clinical read paths, not a migration of existing hospital data or a unified frontend. Adoption of an actual source requires a separately approved record-UUID/source-identity provisioning and migration plan, ownership review and operational custody. No implicit import/marker insertion is provided.
- Linkage approval is a trusted local operator action with independent identity/record verification. It is not automated identity proofing, two-person approval or an identity-admin HTTP privilege. Direct DB/OS administrators remain privileged. Mutation audit is application-level; clinical-read audit, tamper-proof retention and production compliance are not implemented.
- Streamlit sessions and historical credentials remain separate. No existing page is retrofitted with this authorization; legacy clinical ownership weaknesses remain unverified. No browser workflow, actual inference, scan access or treatment generation was tested/enabled. Clinical suggestions remain experimental and subject to clinician review.
- The local WSGI reference server, loopback transport and socket timeouts are for local validation. Production serving/TLS/service identity, distributed throttling, total request deadlines, operational resilience/load, MFA, clinical writes and appointment-to-encounter workflow remain future work.
- Revocation applies to subsequent online validations; in-flight reads already authorized may finish. There is no distributed atomicity across authority/sidecar/source. A trusted source owner must keep source/record UUIDs immutable and never relabel a different person with an old UUID.

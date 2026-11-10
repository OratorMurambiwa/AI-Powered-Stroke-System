# Milestone 3 verification — 2026-11-10

Baseline: `c806145f064ca6b756851c2e44f6ef6392fbee69`. Scope is synthetic booking-to-assessment intake, emergency intake, durable retry/cancellation behavior, versioned contracts and clinical-read auditing. See [appointment/encounter v1](appointment-encounters-v1.md) for exact protocol and limitations.

## Executed verification

| Check | Verified result |
| --- | --- |
| `bash scripts/test-clinical-bridge.sh` | Clean serial run completed successfully: private tmpfs MongoDB, locked npm installation, strict build, all Node/Python suites and syntax compilation |
| Node booking/identity regressions | **44 TAP tests passed**, no failures/skips; includes two parent tests, so **42 child scenarios**. All previous coverage is retained; the confirmed-slot uniqueness check now avoids the separate UUID index masking the slot constraint |
| Python clinical/protocol/workflow suite | **57 tests passed**, no failures/skips: **16 previous cross-language linkage cases**, **23 new workflow integration cases**, **18 protocol/configuration/operator tests** |
| Existing Python signup/default-user guards | **4 tests passed**, unchanged |
| Total Python | **61 passed**, including **39 actual cross-language integration cases** |
| Build and syntax | TypeScript build; Python compileall for clinical API and unchanged legacy source packages; shell syntax; `git diff --check` all passed |
| Dependency audit | `npm audit`: **0 reported vulnerabilities**; no new application dependency, requirements or npm lockfile changes |
| Test-runner contention probe | Both test scripts refuse a second runner before any Docker work, using one shared Git-local `flock` lock |

The final full run uses a fresh project and frozen source/build inputs. An initial new test fixture reused one doctor's time slot across cases and correctly hit overlap rejection; distinct future dates fixed the fixture. One intermediate rerun overlapped dependency installation and failed to start an authority fixture; it is **not** success evidence. Both scripts now serialize shared `node_modules`/`dist` access and fixture startup has a bounded readiness wait. The final serial run has no failing or skipped case.

## Workflow evidence (23 real integration cases)

These run the actual compiled Express authority/scheduling routes, actual Python clinical HTTP application, MongoDB transactions/indexes and fresh SQLite source/clinical stores. The Node fixture creates synthetic identities and obtains real signed sessions through HTTP. Signing keys stay inside Node; no signing secret is supplied to Python. Source/linkage approval uses the same local operator services with synthetic approvals. No existing record is an input.

Verified:

- A synthetic patient books a real availability slot through the versioned API. The assigned doctor reserves a UUID request with explicit source/patient/clinician mapping IDs. Python validates the live appointment proof and creates one pending assessment, receipt and clinician assignment. Mongo acknowledges the same encounter UUID. The patient/doctor can read the new record; another patient, unassigned staff and admin cannot.
- Appointment DTO, durable state and receipt fields match the versioned schema fields. New UUIDs remain stable on repeated reads/retries; no historical appointment UUID is fabricated on read.
- Identical requests return the same outcome. Changed bodies and competing intents conflict. Six simultaneous identical scheduled requests persist **one** record/assignment; simultaneous different intents for one appointment admit one. A shared global key used by different appointment owners admits one and cannot rebind the other owner's intent.
- Incorrect patient or clinician mappings produce a durable rejection **without** a clinical record. Exact replay stays rejected; a corrected new request can succeed, or ordinary cancellation can proceed after acknowledged rejection. Direct clinical payload changes cannot alter the command hash reserved in MongoDB.
- Only the assigned doctor can initiate scheduled intake. Patient/admin/technician roles are denied; another doctor sees an inaccessible appointment. Cancelled and completed appointments cannot start a new assessment.
- Cancellation racing reservation admits either cancellation with no clinical record, or reservation/creation with cancellation refused. Both the versioned **and legacy booking cancellation routes** refuse cancellation after reservation/intake. No clinical record is deleted or hidden to repair scheduling.
- A closed loopback target produces a real transport failure and a durable `PENDING` request. Cancellation stays blocked. Restoring the configured service and retrying the same request completes it with the original encounter UUID.
- A test-only HTTP wrapper returns a non-success/malformed acknowledgement **after a real SQLite commit**. Mongo remains pending/reserved; retry reads the immutable receipt and creates no second record or assignment. These are explicit response-fault injections, not naturally occurring production failures or an actual process kill.
- Separate test-only seams inject a failed Mongo workflow update and a zero-match appointment acknowledgement after clinical commit. The Mongo transaction rolls back its final state, retaining a pending reservation. An authenticated retry acknowledges the already committed record without duplicating it. This is not a claim that MongoDB itself was physically stopped.
- Injected SQLite audit failure rolls back record/receipt/assignment creation and leaves the Mongo request pending. Removing the fault and retrying succeeds. No partial clinical grant remains from the rolled-back attempt.
- Allowed, cross-patient denied, admin denied and unauthenticated clinical reads commit audit decisions containing IDs/outcomes, with no demographic/vital payload, email, password or token. A read-audit write failure returns 503 without clinical data; removing the fault restores access.
- Mapped doctors **and technicians** open an unscheduled emergency assessment under an explicit patient-scoped intake grant, without supplying an appointment. Four concurrent identical emergency requests persist one record/assignment. Conflicting reuse, wrong patient, missing/expired/revoked grant, unmapped staff and patient/admin roles are denied.
- Logout/revoked sessions cannot retry an intent or read clinical data. Fresh login for the same doctor/current role generation can resume a pending intent. Actual staff revocation denies further intake/access. No Streamlit session/cookie/header is used.
- Explicit v2 configuration is required. A v2 initializer cannot overwrite/adopt an existing v1 file, and a version mismatch fails without changing its bytes. Original `schema.sql` is unchanged; v2 is a separate fresh schema, not a migration.

## Protocol/regression distinctions

The 18 protocol/configuration tests use controlled HTTP responses to exercise malformed, stale, misbound and revoked proofs, strict identity contracts, missing/wrong store configuration, private-terminal boundaries and error recovery. New appointment-proof tests check actor/session/request/encounter/hash/status/role-generation/expiry binding and rejection of redirects/service errors. These stubs do not prove JWT signature correctness; actual authority signature/session checks remain in the real Node and integration suites.

The 16 earlier linkage integration cases remain intact after moving only fixture helpers to a non-test mixin. They still exercise live authority stop/resume, UUID/ownership/assignment checks, mapping conflicts/revocation, source/store failures and role-generation changes. They are not duplicated by inheritance to inflate counts. Old clinical sources remain read-only during all cases; source bytes are checked before/after (the earlier explicit native-ID-reuse fault restores its own newly generated fixture).

## Isolation and preservation

The helper creates only a run-specific private Docker network and tmpfs MongoDB replica set. The disposable test container has private `/tmp` for synthetic source/clinical DBs and bytecode. Nothing binds a host database/API port; normal Compose services and all existing volumes are untouched. Cleanup removes only owned test containers/network, never persistent volumes or unrelated databases. No raw environment/credential dump or source DB is stored in the repository.

Runtime/test conditions: Node **22.14.0**, npm **10.9.2**, TypeScript **5.9.3**, Python **3.12.16**, SQLite library package **3.48.0-r4**, MongoDB **8.0.17** at the existing pinned digest, existing locked Express/Mongoose/JWT/bcrypt dependencies. Python is installed only into the disposable test container via Alpine 3.21 APK; that test bootstrap snapshot is not a fabricated portable lock. The helpers additionally require existing Git and Linux `flock`; the serialization probe used the installed tool.

Only source/tests/contracts/docs and blank/commented local configuration examples are committed. The historical `data/` Git tree, original SQLite/MongoDB records, scans, model weight, notebook, actual credentials, legacy requirements and dependency lock are unchanged. No inference, hosted AI call, real patient linkage/migration or legacy Streamlit session integration was performed. The source Hospital-booking-system repository remains preserved.

## Remaining limitations

- This is a synthetic-only pending-assessment workflow, not clinical diagnosis, finalization or real emergency care. Unknown-patient/offline break-glass intake, approved real-source adoption and a shared frontend remain unimplemented. A patient grant is not inferred from a name/email/code or a staff role.
- MongoDB and SQLite do not share a transaction. There is no distributed exactly-once claim. Pending requests require authenticated client retries; no bearer token or background retry worker is persisted. A permanently revoked clinician/changed mapping or unresolved storage conflict can require manual operator review. No unsafe force-unlock/abort path exists.
- Ordinary cancellation is blocked while an assessment is reserved and after it is created. Care completion, reassignment, rescheduling and reviewed cancellation after intake need a separate domain workflow; historical clinical records must be retained.
- Authority/link revocation applies to subsequent validations; already authorized in-flight work may finish. Local clinical audit is an authorization/mutation history, not tamper-proof retention or a byte-level delivery/compliance certificate. Audit review/export/retention and metadata protection remain operational work.
- Loopback transport, the threaded WSGI reference server, socket timeouts and serialized SQLite audit writes are local prototype choices, not production TLS/service identity, absolute-deadline, throughput, availability or clinical-safety guarantees. Staff identity proofing, MFA and distributed abuse protection need production review.

# Milestone 5B verification — 2026-11-10

Baseline: `4f3cde5b37436bbe4e0d51e36f83db8678fe1085`. Scope: unified synthetic clinical portal and identity administration using the existing authority, clinical API and real isolated CPU classifier. See [launch commands](../portal/README.md), [discovery contracts](clinical-portal-v1.md) and [integration plan](hospital-integration-plan.md).

## Implemented behavior

Patient appointments remain working. An assigned doctor starts assessment intake for an owned confirmed appointment using live explicit patient/doctor mapping UUIDs and the existing reservation/proof protocol. Discovery lists only mapped/assigned new assessment encounters; patients discover only their own approved workflows. An explicitly assigned technician records vitals/NIHSS, uploads validated private PNGs and submits. Assigned doctors add internal notes and independently reject/approve human summaries. Patient results omit internal notes/history and every experimental prediction, including acknowledged predictions. Authenticated audited PNG downloads use short-lived Blob URLs, never public storage paths or bearer URLs. Emergency encounters remain supported by existing APIs and discovery; no new emergency-intake screen is claimed.

Doctors alone invoke/review the exact trusted MedStroke artifact on an existing private scan. Prediction provenance stays separate from approved human observations and is labeled experimental, uncalibrated and subject to independent review. No automatic diagnosis, tPA decision, prescription, hosted AI, legacy Streamlit authentication or model substitution is introduced. Approved results remain immutable.

Administrators use the existing password-reauthenticated staff provisioning, role/revocation and audit APIs. Invitations show only a delivery UUID; private terminal handoff consumes the existing one-time delivery after recipient verification. Activation/recovery sets a new password through existing APIs; public recovery stays generic. No public staff signup/default credential/token-retrieval endpoint exists. Admin identities cannot access clinical workflows.

Clinical writes retain the exact versioned UUID command in memory for explicit retry after uncertain transport, blocking other writes until resolved. Intake can recover the persisted request UUID. Current server roles, session revocation, link generations, assignment checks, optimistic versions and audit persistence remain authoritative. MongoDB scheduling and SQLite clinical storage remain separate; no cross-database atomicity, automatic account matching or background reconciliation is claimed.

## Verification results

| Check | Verified result |
| --- | --- |
| Node booking/identity HTTP regressions | **45 TAP tests passed**, zero failed/skipped |
| Python clinical/protocol/real-authority integration | **109 passed** |
| Isolated real CPU model worker | **5 passed**, including deadline recovery and credential-free offline environment |
| Legacy public-signup guards | **4 passed** |
| Total Python regressions | **118 passed**; browser journeys reported separately |
| Frontend component/adapter tests | **22 passed**, 3 files; controlled transports, distinct from real browser evidence |
| Frontend production build | Strict TypeScript and Vite passed; JS 269.09 kB / gzip 81.83 kB, CSS 12.59 kB / gzip 3.72 kB |
| Frontend dependency audit | **0 reported vulnerabilities**, locked npm install |
| Real Chromium scheduling journeys | **11 passed**, 96.595s |
| Real Chromium clinical/identity journeys | **4 passed**, 77.794s |
| Total browser journeys | **15 passed**, no route mocks; Chromium 140.0.7339.16 |
| Static/artifact checks | Shell syntax, Python AST/compile, contract JSON, diff whitespace, bundle/secret/path review passed |

The final `bash scripts/test-clinical-bridge.sh` exited successfully: worker 5 tests in 10.401s, Node 45 in 68.152s, clinical 109 in 143.641s and legacy 4. Both backend build/typecheck and package audit passed (zero reported vulnerabilities). No test was skipped, and actual model inference is retained in the integration cases. The fresh demo launch reran all 22 frontend tests, strict build and npm audit after formatting. The fresh `start`, `test`, `stop` cycle completed successfully. Runtime uses the existing Node 22.14.0, locked React/Vite dependencies and pinned MongoDB 8.0.17; JavaScript dependencies were not upgraded. All browser fixtures use newly generated synthetic accounts and stores. Desktop 1440px and mobile 390px clinical screenshots were visually inspected; the browser asserted no mobile horizontal overflow. Screenshots/logs remain ignored. Demo cleanup removed only owned disposable services and private generated credentials; no persistent volume was deleted.

## Real browser and API evidence

The 11 prior scheduling journeys still verify registration, empty browser token storage, booking/cancellation, doctor availability management, cross-patient appointment isolation, expired sessions, logout/logout-all, role restrictions, actual listener outages, conflict handling, keyboard navigation and mobile rendering. Session expiry uses a private fixture-only stored-session expiration, not a claim that tests waited 15 minutes. Service outages stop actual local listeners; no HTTP route is mocked.

The four new clinical/identity journeys verify:

1. Real patient booking → doctor confirmed-appointment intake → explicit private technician assignment → doctor note → technician vitals/NIHSS → malicious SVG rejected as PNG → actual synthetic PNG upload → submission → isolated real CPU inference → doctor acknowledgement → human rejection → technician resubmission → independent doctor approval → patient's approved-only results and authenticated scan download. The downloaded bytes exactly match the synthetic upload. Internal doctor notes and every prediction endpoint remain unavailable to the patient.
2. Another patient receives 404 for assessment/scan references; assigned technician prediction reads receive 403; admin clinical API/navigation is forbidden.
3. Stopping the actual Python clinical listener makes a doctor note fail with 503. Restoring it and explicitly retrying sends exactly the same request body/idempotency key/version and creates one note.
4. Admin password-reauthenticated invitation → private one-time activation delivery → new staff password setup/login → no clinical access without explicit linkage → role change invalidates a previously confirmed live technician session → a fresh doctor login works → revocation invalidates that confirmed live session and blocks future login. Recovery still returns the generic public message. The test does not log out the staff session before asserting invalidation.

Actual gray 64×64 synthetic PNG result: **normal**, raw score **0.9984942674636841**, scores `[0.0003050427767448127, 0.0012006619945168495, 0.9984942674636841]`, worker job **2578.116 ms**. Scan SHA-256: `50c3286a9162b050472880e6350080c5330a82b8e7eea94a07907416b0f72510`; model SHA-256: `200f5ab52415cb96dae577a45b5d1cb8a6dedb2cbab03c32885d826553d0d595`. This is real inference on nonmedical generated pixels, not an accuracy/calibration claim; the worker duration excludes startup and is not end-to-end browser latency. The independent human summary explicitly approves no model diagnosis/treatment. Model review and human approval remain separate records.

An earlier browser run passed the clinical journey/isolation/outage cases but failed staff setup at an ambiguous nested select label. Explicit accessible select names fixed it; the full fresh final 15-case run passed. Earlier npm transport/startup diagnostic attempts and the initial worker failures are not counted as successful final verification. The final launch used frozen formatted application/scripts, unlike an earlier interrupted diagnostic launch that was edited while executing.

## Worker startup correction

Repeated initial runs stopped at the real worker's cold startup gate. Profiling a networkless bounded diagnostic showed torch import consuming approximately 16 CPU seconds, exceeding the previous 12-second whole-exec CPU limit before scan inference; the process exited 137 with Docker OOM false. Ultralytics import also attempts a DNS connectivity probe unless explicitly offline. These failed attempts are not successful regression evidence.

The worker now loads the hash-pinned trusted artifact once in a single-threaded **credential-free supervisor**, within a separate **60-second startup bound**, before HTTP readiness. Ultralytics offline/autoinstall settings prevent network probing/installation. Each admitted scan forks a fresh child, retaining **12 CPU seconds / 20 wall seconds**, PNG/hash validation and container limits. A timed-out child is killed/reaped; broken supervisor IPC fails closed and kills the group. The parent service key/JWT/clinical credentials are excluded from the supervisor/child environment. The model digest is checked per scan. A real synthetic inference still gates readiness. Reported durationMs now excludes framework/model startup; comparisons with old cold-exec latency are invalid. Model bytes, labels and preprocessing are unchanged. Focused tests exercise real inference, bad inputs, hash mismatch, deadline/recovery and environment isolation, rather than substituting mock prediction evidence.

## Isolation and security review

The demo creates a new marked synthetic tmpfs MongoDB and fresh temporary SQLite v4 source/link store. Explicit fixture-native references and live identity proofs create links; bootstrap proof sessions are then revoked. Technician assignment is a separate private operator action. Clinical source mounts contain code only; existing patient databases/scans are never mounted. Only the worker receives the original trusted model read-only. Runtime keys/passwords are newly random, private and ignored; browser bundles contain none. Stop removes only labeled owned containers/networks and generated private runtime files, without deleting persistent volumes or touching normal services.

Browser JWTs remain in memory only; live `/me`, expiry/revocation checks, stale-response guards and 401 cleanup remain intact. The same-origin gateway preserves authenticated scan headers/CSP. Responses are no-store; untrusted clinical/model strings are escaped React text. The model service remains private/internal with one admitted job, no queue and no hosted fallback. Source/contract additions contain no raw patient data, credentials or inference artifacts. Legacy Streamlit code, root dependency locks, original database/scan/model trees and the original booking repository are preserved.

## Remaining work

This is a local synthetic demonstration, not real-patient adoption or a clinical accuracy evaluation. Training provenance/accuracy/calibration remain unverified despite the user's explicit trust confirmation of the exact artifact. Synthetic pixels cannot establish diagnostic performance. Human approval and model review are deliberately separate, and patients never receive model records.

General linkage/assignment administration, emergency-intake UI, pagination (clinical/staff cap 100, scheduling cap 200), booking idempotency, active doctor directory, hospital timezone/DST policy, notifications, production delivery, background intake reconciliation and operational recovery tooling remain work. Approved encounters retain existing appointment-cancellation locks. Production TLS/gateway review, MFA, distributed throttling, key management, clinical/privacy validation, full accessibility evaluation and broader browser coverage are not established here. No existing accounts or records are automatically adopted.

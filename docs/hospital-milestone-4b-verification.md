# Milestone 4B verification — 2026-11-10

Baseline `f68548f446a9432200079fb22ef7138d8afd79b6`. Scope: explicitly trusted existing MedStroke checkpoint, separately isolated local CPU execution, versioned private experimental predictions and doctor-only acknowledgement/dismissal. See [artifact audit](experimental-models/medstroke-audit.md), [actual CPU outputs](experimental-models/medstroke-cpu-probe-v1.json) and [prediction contract](experimental-predictions-v1.md).

## Trust gate and actual inference

The existing artifact hash is **200f5ab52415cb96dae577a45b5d1cb8a6dedb2cbab03c32885d826553d0d595**. User explicitly confirmed this intended trusted fingerprint before loading. Its original bytes remain unchanged. Non-executing ZIP/pickle opcode audit, exact class allowlist and restricted CPU load confirmed labels 0 bleeding / 1 ischemia / 2 normal and 224-pixel RGB/bilinear-resize/center-crop/tensor01 preprocessing. Legacy labels.txt is empty, README calls the artifact a placeholder, and embedded Ultralytics 8.3.221 conflicts with the legacy 8.3.0 pin. No training provenance or clinical accuracy is established by the user's hash confirmation.

Actual inference ran **before API enablement**, in a nonroot, networkless container using the original read-only artifact, restricted `weights_only=True` loading and resource limits:

| Generated 64×64 pattern | Actual raw class | Raw max score | Child duration, including imports/loading |
| --- | --- | --- | --- |
| Black | bleeding | 0.39370256662368774 | 7209.852 ms |
| White | normal | 0.3774694502353668 | 7345.568 ms |
| Gradient | normal | 0.46912384033203125 | 6473.736 ms |

These are successful execution probes on **nonmedical images**, not correct/incorrect clinical diagnoses, accuracy or performance guarantees. Full score vectors/input/model/preprocessing digests are retained in the linked sanitized JSON. No patient scan or existing clinical database was an input. The first nonroot import probe needed explicit USER/cache settings; the corrected restricted audit/load and three forward passes passed. Missing and deliberately untrusted synthetic artifact probes also passed: refusal occurred **before torch import/deserialization**, in a new tmpfs container without mounting the original model.

## Final regression results

Final `docker build -f inference_worker/Dockerfile -t stroke-inference:milestone4b .` and `bash scripts/test-clinical-bridge.sh` exited **0**.

| Suite/check | Actual result |
| --- | --- |
| Node booking/identity | **44 TAP tests passed**, 42 child cases + 2 parents, no failures/skips |
| Python clinical | **104 passed**: original 83 cases + **16 new real cross-language prediction cases** + **5 controlled worker-protocol cases** |
| Standalone isolated worker | **4 passed**, actual CPU forward passes/invalid inputs/hash mismatch/forced child deadline and subsequent real execution |
| Existing legacy signup/default-user guards | **4 passed**, unchanged |
| Total Python | **112 passed**, including **81 real clinical/authority cross-language integration cases** (previous 65 + new 16) |
| Dependencies/build | Strict TypeScript build, npm ci and npm audit (**0 reported vulnerabilities**); final worker image matches all **35 actual frozen packages** in its new constraints lock |
| Static checks | Python compilation/AST parse, shell syntax, all contract JSON parsed, `git diff --check` passed |
| Final packaging | Explicit source-only COPY/ignore rules exclude a synthetic env canary; packaged Python hashes exactly match tested sources; rebuilt image passed another actual CPU smoke |
| Artifact rejection | Actual missing/untrusted synthetic checkpoint refusal before deserialization; original weight hash unchanged |

The five protocol cases use controlled local HTTP responses, not model inference. They check model/input/preprocessing binding, booleans/non-finite/inconsistent scores, wrong labels/schema, redirects, malformed/oversized responses and recovery; they are **not** counted as real classifier evidence. An attempted separate host invocation could not bind a loopback socket under the host sandbox and is not counted as success. The same cases passed in the final isolated Docker suite. No mocked successful inference replaces an actual forward pass in the worker/integration evidence.

Secret review additionally found that the initial broad directory context rule could include a future ignored env file. A synthetic canary exposed Docker directory-exception precedence, then explicit child exclusions and explicit COPY filenames fixed it. The final canary exclusion/source-hash checks and actual CPU smoke passed. No real credential was included; only the deliberately synthetic sentinel appeared in the rejected packaging attempt. Runtime Python/dependency sources remained identical to the full passing regression run, so the packaging-only change was verified by source hashes and the new real smoke rather than claiming another full suite execution.

## New integration evidence (16 cases)

Tests run the actual compiled Express identity authority, MongoDB fixture and actual Python clinical application against fresh synthetic v4 stores. The inference service runs on a separate **internal** Docker network. The caller joins that network plus the isolated MongoDB test network; no host port is exposed. Tests use only generated PNGs, synthetic identities and independently approved synthetic links/assignments.

Verified:

- An assigned doctor requests inference on an existing private encounter scan. The real worker returns a validated versioned record with exact input/model digests, checkpoint/preprocessing versions, raw three-label scores, requester mapping/role generation and requested/completed timestamps. Doctor review records an explicit attestation and note without approving any diagnosis.
- Patient, other patient, admin, assigned technician, unlinked/unassigned staff and unauthenticated requests cannot obtain classifier output. Supplying a role/model/path/URL or wrong schema cannot change privileges/input selection. An existing scan from patient A cannot be rebound to a different patient B encounter even when the doctor has legitimate assignments to both.
- Three concurrent identical requests produce one committed prediction and one actual attempt; concurrent callers can receive 202/PENDING. Repeated completed requests return the same record/ID. Changed request bodies cannot rebind the intent. Competing reviews admit one immutable decision; exact review replay returns it and changed decisions conflict.
- Real refused-loopback worker transport produces FAILED/no-score metadata. Restoring the actual worker permits the same intent/record ID to succeed on attempt 2. Disabled configuration fails closed. Three failed attempts exhaust the retry bound. Corrupt stored input fails before creating a job.
- An explicit test-only fence/clock mutation during a **real** inference job prevents stale output from committing. A later authenticated retry with a new lease succeeds; no production force-unlock route exists.
- Logout while a real model job runs causes post-execution live identity validation to deny completion/disclosure; no score persists. A new authorized login can retry. Revoked assignment denies further read/review/request/replay.
- A test-only SQLite completion-audit trigger aborts the transaction containing the real result; successful state/result do not persist. Failure metadata is retained, and removing the fault permits an authenticated real-worker retry. Failed read audits suppress prediction history disclosure.
- A fully approved human assessment is unchanged before/after real inference and doctor prediction review. The patient receives the exact same approved human projection, with no classifier fields, and remains forbidden from prediction endpoints even after acknowledgement.
- The real private worker rejects an incorrect admission key and malformed SVG input. Fresh v4 initialization/refusal leaves an existing v3 file's bytes unchanged. All prior scheduling/intake/emergency/assessment/scan/revocation/approval cases still run once and pass.

A closed port is a real transport refusal, not a claimed worker process kill. Audit triggers and fence-clock changes are explicit test seams; they are not claims of physical SQLite failure or production force-unlock. The standalone deadline test actually launches and kills a child, then executes a new real job successfully. Execution may be recomputed after unknown outcomes; only fenced committed records are idempotent, not model CPU execution itself.

## Runtime and preservation

Worker: Python 3.12.11 pinned base digest; torch 2.10.0+cpu / torchvision 0.25.0+cpu, Ultralytics 8.3.221, NumPy 2.2.6, Pillow 11.3.0 and **actual** 35-package lock. The worker image contains no model, DB, scan, clinical credentials or unrelated app source; Dockerfile-specific context filtering limits it to worker code plus the PNG validator/error class. Nonroot/read-only runtime, 64 MiB tmpfs, 2 CPUs, 1500 MiB RAM, 64 PIDs, dropped capabilities/no-new-privileges; single admitted job, 20-second parent wall limit, 12 CPU-second child limit and kill/reap of the process group. Parent credential is not forwarded into the child. API stays on its existing dependency set; legacy requirements/lock are unchanged.

The test helper generates a temporary mode-0600 random key env file and cleans only its own test containers/networks/file. It never deletes/prunes persistent volumes or touches normal services/data. SQLite fixtures remain separate, source byte hashes are checked after each test, and worker inference receives only scan bytes/hash/pinned model digest, not identity JWTs or demographics. No original DB, uploaded scan, credential, model weight or notebook is modified/committed. Historical data/model tree entries remain unchanged. No legacy Streamlit login, hosted OpenAI/LLM call, autonomous treatment/tPA logic or cloud deployment is introduced.

Staged source/contracts/tests/docs/actual public dependency lock and sanitized synthetic measurements are reviewed for secret/private-key patterns and forbidden artifacts; generated build/cache/env/database/model/image files are excluded. Existing Git author identity is retained, with no AI coauthors or force-push.

## Unresolved work

- Training provenance, clinical accuracy/calibration, dataset representativeness/leakage/subgroups and diagnostic suitability remain **unverified**. User trust confirmation is limited to this artifact hash. No real patient use is validated.
- Fresh opt-in v4 synthetic store only; no existing v1/v2/v3 adoption/migration, unified frontend or clinical DICOM pipeline. Original legacy loader/treatment paths remain separate and unexecuted.
- Acknowledgement/dismissal never turns a classifier label into an approved finding. Patients never see prediction records. Future clinically governed interpretation/adoption/amendment requires separate design and validation.
- Cold child startup costs several seconds per request; one admitted job and finite quotas/retries are prototype safeguards, not throughput/SLO evidence. Busy/outage/revoked/permanently changed mapping or exhausted attempts can require operator review; no background reconciliation.
- Private local HTTP admission key and container restrictions are not production TLS/mTLS, operator identity proofing, key rotation, ingress-wide absolute deadlines, distributed throttling, encrypted storage/backups or tamper-proof audit retention. NumPy/Pillow/torch/Ultralytics compatibility is verified for this checkpoint/runtime/probe, not all future versions. npm audit is not a complete inference-image CVE/security certification.

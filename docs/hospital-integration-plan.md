# Hospital appointments + experimental stroke assessment: integration plan

## Inspected baseline and preservation

Source inspection used the actual code at:

- [AI-Powered-Stroke-System `3e462ac`](https://github.com/OratorMurambiwa/AI-Powered-Stroke-System/tree/3e462ac7ec98667a1b40dabc5fd6ad068ed75377).
- [Hospital-booking-system `2114faa`](https://github.com/OratorMurambiwa/Hospital-booking-system/tree/2114faa0bc21eb759b7728eb0194867d679b9c70).

The booking source remains unchanged: no commits or pushes target that repository. A code-only adaptation lives in `booking-backend/` in the stroke repository, with the source attribution retained. Work uses a separate checkout because the existing local stroke checkout has unstaged changes (primarily line endings); those edits and the unrelated IncidentIQ project are not staged or changed.

Only source code and file metadata were inspected. The existing `data/stroke.db`, uploaded scans/annotations, credentials, model weights and notebook were not opened for patient inspection, executed, migrated or modified. The sparse working tree excludes `data/`; the commit retains the existing Git tree entries unchanged, rather than copying or committing new databases/scans. No clinical application startup, inference, hosted LLM call or existing database migration was performed. Dependency downloads and Git operations are the only remote operations for this milestone.

## What the implementations actually do

### Stroke app

This is a Python **Streamlit multipage app**, not an existing FastAPI/REST service. `core/database.py` creates a SQLAlchemy engine for a hardcoded relative SQLite `data/stroke.db`; `models/{user,patient,visit,treatment}.py` model clinical records. User keys are SQL integer IDs; patients also have a `P###` code, and doctor assignment uses usernames. `services/user_service.py` supports bcrypt plus legacy SHA-256 password verification. At baseline, home/signup code allowed physician/technician registration and automatically seeded known-password demo staff on an empty database.

`services/scan_service.py` and `ml/predict.py` load a local Ultralytics classifier and expose model scores. `services/tpa_service.py` implements heuristic eligibility logic. Treatment suggestions have **two hosted OpenAI call paths**: `services/ai_service.py` and inline code in `pages/d_view_case.py`, using patient/visit details. Those paths are not a validated clinical service, and were not invoked. Treatment text and finalization live in the existing workflow; experimental model output is not proof of diagnosis, eligibility or safe prescribing. The inline/service duplication, SDK response handling, authorization/record ownership, legacy password hashes, known existing demo credentials and unvalidated clinical logic need separate remediation. Do not enable hosted generation with real patient information.

### Booking app

The entire repository is 22 root-level TypeScript/package files. `tsconfig.json` includes `src/**/*` with `rootDir: src`, while controllers/routes import nonexistent `../models`, `../config`, `../utils` directories. The config `index.ts` is at root; `user.ts` has different case from imports; `Availabilty.ts` and `availabilty.controller.ts` are misspelled. There was no lockfile and `npm test` only printed a message.

The intended stack is Express 4 + Mongoose/MongoDB, JWT/bcrypt, Redis cache and BullMQ. Appointment creation/cancellation already attempted MongoDB transactions, but assumed replica-set support without gating startup, used read-then-save slot mutation, did not retry transient transaction conflicts, lacked a unique confirmed-slot invariant, and could fail after commit while invalidating cache/queuing a notification. Availability allowed overlaps and arbitrary `isBooked` edits or deletion of booked slots. Signup trusted the supplied `role`. The default JWT signing secret was public. The notification workers simulated sending and logged recipient/message details; they were not real email/SMS integration. No booking frontend exists in that repository.

## Milestone 1 — implemented

1. Add a source-attributed `booking-backend/` copy with conventional `src/config`, `controllers`, `middleware`, `models`, `routes`, `utils`; correct spelling/casing and imports, restore strict compilation and generate an actual npm lockfile.
2. Patient-only public registration, bounded scalar validation, normalized email, bcrypt byte limit, no default JWT secret, HS256 verification, and authorization from current stored roles. No public privilege-assignment endpoint. Reject MongoDB operator input. Staff require trusted operator provisioning; tests provision synthetic staff directly.
3. Serialize doctor schedule writes through a transactional persisted doctor update; reject overlapping intervals. Owned booked slots cannot be edited/deleted or reopened through request fields. Admin is not implicitly a clinician.
4. Claim slots atomically and persist appointment/claim in one retrying MongoDB transaction. Enforce one confirmed appointment per availability ID in a partial unique index. Cancel only a current confirmed owned appointment and release its slot atomically. Fail startup without replica-set support or initialized indexes.
5. Omit Redis caching and simulated notification workers from this first copy; no post-commit Redis dependency or misleading delivery promise. No actual external messaging is introduced.
6. Close legacy stroke public staff signup at the service boundary and remove staff signup forms; disable automatic default-user creation. Existing stored users/data remain unchanged. Put experimental/clinician-review warnings on prediction/treatment and case-summary screens.
7. Add synthetic real-MongoDB HTTP/concurrency/rollback tests, pure Python signup guard tests, reproducible Docker test tooling and verified results.

## Milestone 2A — shared identity authority implemented

The TypeScript booking backend is the authority for new shared identities and versioned online introspection. Canonical patient/doctor/technician/admin roles use current persisted authorization; legacy physician maps to doctor at the boundary without a data migration. Existing SQLite/Streamlit identities remain separate and grant no booking access.

Session-backed JWTs expire in at most 15 minutes; logout, password changes/recovery, staff role changes and revocation invalidate sessions durably. Staff onboarding requires authenticated admin password recheck and an audited activation flow. A CLI-only one-time opt-in bootstraps the initial invited administrator, with no known default credential. Recovery/activation tokens are single-use, 15-minute and hash-stored, with an encrypted local operator delivery adapter; no email/SMS service is enabled. Audits and security changes commit together. Identity admins and technicians cannot read appointment content. Actual cross-patient, concurrency, revocation, recovery and rollback checks are recorded separately.

See [identity v1 contracts and procedures](identity-v1.md) and [milestone 2A results](hospital-milestone-2a-verification.md). No existing users/data were migrated or automatically matched by name/email. Future approved clinical linkage, per-record clinical authorization and the unified frontend remain unimplemented.

## Milestone 2B — explicit synthetic clinical identity linkage implemented

The isolated `clinical_api/` package validates live booking sessions through a separate versioned clinical-introspection contract. Local operator approvals bind exact authority subjects to source-scoped stable clinical UUIDs, with no name/email/code matching. Doctor/technician access requires an explicit encounter assignment tied to the active mapping ID and current role generation. Admin status grants no clinical access. Duplicate/conflicting mappings, source/record identity drift, stale role generations and unavailable stores fail closed. Link/assignment changes and approvals are audited transactionally.

Only fresh marked synthetic clinical sources and a separate mapping SQLite store are supported in this milestone. Original Streamlit/SQLite records, credentials, scans and weights remain untouched and unintegrated. New read-only paths expose minimal owned/assigned records, not scans, predictions or treatment generation. See [clinical linkage contracts/procedures](clinical-linkage-v1.md) and [2B verification](hospital-milestone-2b-verification.md).

## Milestone 3 — synthetic booking-to-assessment workflow implemented

New versioned appointment UUIDs and durable MongoDB assessment intents connect to Python's explicitly initialized clinical store v2. Scheduled intake requires the assigned doctor, exact approved patient/clinician mapping IDs and live reservation proof. SQLite commits the new assessment record, assignment, receipt and audit together; Mongo acknowledges separately. Unknown outcomes remain pending/reserved for authenticated retry; immutable rejection alone releases the reservation. No distributed atomicity or automatic background sender is claimed. Explicit patient-granted doctor/technician emergency intake needs no appointment. Supported clinical reads now require committed allow/deny/failure audit events before disclosure.

Original source stores remain read-only; there is no in-place v1 upgrade or historical UUID backfill. Existing Streamlit/credentials/scans/models remain separate. See [appointment/encounter v1](appointment-encounters-v1.md) and [Milestone 3 results](hospital-milestone-3-verification.md) for exact states, cancellation limits, schema contracts and actual verification.

## Milestone 4A — synthetic human assessment and review

The explicitly initialized v3 clinical store extends scheduled/emergency encounters with attributed vitals/NIHSS observations, private bounded PNG blobs, internal doctor notes and revisioned submit/approve/reject actions. SQLite atomically commits immutable request receipts, snapshots, provenance and mutation audits. Live authority/assignment checks protect every action and download; patients receive only their own immutable clinician-approved projection. No ML/treatment/hosted AI or legacy login path is enabled. v1/v2 stores and original sources are not upgraded/adopted. See [assessment workflow v1](assessment-workflow-v1.md) and [4A verification](hospital-milestone-4a-verification.md).

## Milestone 4B — isolated experimental CPU classifier

After an explicit user trust confirmation for the existing checkpoint hash, non-executing artifact/loader audit and actual networkless CPU verification, a separate restricted worker serves only the pinned MedStroke artifact. Opt-in fresh clinical store v4 records doctor-requested private-scan predictions with model/input digests, preprocessing version, raw scores, timestamps, durable fenced retries and audit. Doctor acknowledgement/dismissal remains separate from observations and immutable approved findings; predictions are never patient-visible and drive no tPA/treatment decisions. Training/accuracy provenance remains unverified. See [artifact audit](experimental-models/medstroke-audit.md), [prediction v1](experimental-predictions-v1.md) and [4B results](hospital-milestone-4b-verification.md).

## Subsequent integration milestones

### 2C. Approved clinical adoption and production identity hardening

Milestone 2A selected the booking authority and implemented local audited staff/session/recovery controls. Before production, review hospital staff verification, MFA, distributed throttling, transport authentication, key custody and approved delivery. Canonical doctor/physician normalization and a least-privilege technician role are implemented for booking. Review all Streamlit direct-page authorization and patient ownership checks before exposing clinical records. Existing known demo accounts must be disabled/reset explicitly by an authorized operator, not by silently editing preserved databases. Patient code alone is not sufficient identity verification for clinical access.

Milestone 2B now uses explicit source UUIDs and immutable person/encounter UUIDs bound to exact native primary keys; no patient code or clinician username is an identity join. Before adopting any actual clinical source, obtain a separate approved data/record-identity provisioning and migration decision, source UUID custody, audited operational access and record-ownership review. Never auto-link by name/email/code or auto-import current patient data. Rehearse future changes only against generated synthetic fixtures.

### 3B. Care lifecycle and operational scheduling hardening

Milestone 3 implements versioned appointment/intake/receipt contracts, explicit scheduled ownership and patient-granted unscheduled intake. Extend them with reviewed care completion, reassignment/cancellation after intake, operational pending-request reconciliation and a production emergency policy. Unscheduled intake does not require a booking; actual emergency operations remain outside this synthetic prototype. Choose hospital timezone/DST policy, scheduling granularity, clinician/patient overlap policy, pagination and idempotent booking request keys. The current invariant prevents doctor/slot double booking; it does not prevent a patient booking two different doctors simultaneously.

Keep Mongo scheduling and SQLite clinical data separate initially behind narrow APIs. Do not make cross-database writes appear atomic. Use an outbox/idempotent consumer if encounters or notifications later span services. Existing standalone MongoDB data would require an explicit replica-set/index preflight; do not point this milestone at such data.

### 4C. Unified portal and clinical validation boundary

Build the shared patient/staff portal after contracts and identity are agreed. Do not treat booking JWTs as Streamlit authentication automatically. Milestone 4A supplies synthetic server-side observations, private PNG delivery and audited human review; a shared frontend and approved real-source adoption are still required. Add structured provenance (model/version, inputs, time, uncertainty) and distinct generated-draft versus clinician-approved treatment fields. Keep explicit experimental labeling, clinician attestation and no autonomous treatment execution. Consolidate the duplicate hosted generation paths, default external generation off, and evaluate any local model separately on synthetic/de-identified approved evaluation data. Model percentages must not be advertised as validated clinical confidence.

### 5. Operational verification

Synthetic end-to-end journey: patient registers → sees clinician availability → books → authorized technician creates an assessment encounter → experimental analysis → clinician reviews/approves → patient sees only approved results. Verify forbidden role access, record ownership, upload validation, no payload/credential logging, concurrency, retries and audit history. Add frontend/browser tests, notification outbox tests and controlled migration/recovery drills. Perform security/privacy and clinical validation before handling real hospital data. No cloud deployment, paid services or remote repository creation is authorized by this milestone.

## Current limits

New synthetic clinical read paths now validate booking identities and explicit linkage, but the original Streamlit system remains separate and there is no unified frontend. The original stroke runtime and real model inference are unverified here. UI warnings are source changes with syntax checks, not browser verification. Booking now has audited admin provisioning APIs, local encrypted recovery/activation handoff and revocable bounded sessions. It still has no staff provisioning UI, refresh token flow, pagination, local hospital timezone, automated notification delivery, booking-creation idempotency key or production deployment hardening; encounter-intake idempotency is implemented in milestone 3. MongoDB direct writes outside the API can violate interval overlap policy; the confirmed-slot unique index remains a separate database invariant. Six concurrent requests are regression evidence, not a capacity or production safety claim. See [verified results](hospital-milestone-1-verification.md).

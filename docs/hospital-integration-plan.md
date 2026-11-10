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

## Subsequent integration milestones

### 2B. Clinical identity linkage and production identity hardening

Milestone 2A selected the booking authority and implemented local audited staff/session/recovery controls. Before production, review hospital staff verification, MFA, distributed throttling, transport authentication, key custody and approved delivery. Canonical doctor/physician normalization and a least-privilege technician role are implemented for booking. Review all Streamlit direct-page authorization and patient ownership checks before exposing clinical records. Existing known demo accounts must be disabled/reset explicitly by an authorized operator, not by silently editing preserved databases. Patient code alone is not sufficient identity verification for clinical access.

Define a new stable patient identifier and a versioned, explicitly approved mapping between Mongo ObjectIds, SQL user/patient integers, `P###` codes and clinician usernames. Never auto-link by name/email or auto-import current patient data. Rehearse migrations only against generated synthetic fixtures; preserve originals and require a separate migration decision.

### 3. Scheduling and encounter API contracts

Define versioned API contracts and consistent error envelopes for patient profiles, clinicians, availability, appointments and assessment encounters. An appointment references a patient and clinician; an assessment encounter links explicitly to the appointment when appropriate. Unscheduled emergency assessment remains possible and must never be delayed by booking. Choose hospital timezone/DST policy, scheduling granularity, clinician/patient overlap policy, pagination and idempotent booking request keys. The current invariant prevents doctor/slot double booking; it does not prevent a patient booking two different doctors simultaneously.

Keep Mongo scheduling and SQLite clinical data separate initially behind narrow APIs. Do not make cross-database writes appear atomic. Use an outbox/idempotent consumer if encounters or notifications later span services. Existing standalone MongoDB data would require an explicit replica-set/index preflight; do not point this milestone at such data.

### 4. Unified portal and experimental clinical boundary

Build the shared patient/staff portal after contracts and identity are agreed. Do not treat booking JWTs as Streamlit authentication automatically. Extract server-side clinical operations into a supported API with ownership checks, private scan access and audited clinician review. Add structured provenance (model/version, inputs, time, uncertainty) and distinct generated-draft versus clinician-approved treatment fields. Keep explicit experimental labeling, clinician attestation and no autonomous treatment execution. Consolidate the duplicate hosted generation paths, default external generation off, and evaluate any local model separately on synthetic/de-identified approved evaluation data. Model percentages must not be advertised as validated clinical confidence.

### 5. Operational verification

Synthetic end-to-end journey: patient registers → sees clinician availability → books → authorized technician creates an assessment encounter → experimental analysis → clinician reviews/approves → patient sees only approved results. Verify forbidden role access, record ownership, upload validation, no payload/credential logging, concurrency, retries and audit history. Add frontend/browser tests, notification outbox tests and controlled migration/recovery drills. Perform security/privacy and clinical validation before handling real hospital data. No cloud deployment, paid services or remote repository creation is authorized by this milestone.

## Current limits

The two systems are not yet wired together and there is no unified frontend. The original stroke runtime and real model inference are unverified here. UI warnings are source changes with syntax checks, not browser verification. Booking now has audited admin provisioning APIs, local encrypted recovery/activation handoff and revocable bounded sessions. It still has no staff provisioning UI, refresh token flow, pagination, local hospital timezone, automated notification delivery, request idempotency key or production deployment hardening. MongoDB direct writes outside the API can violate interval overlap policy; the confirmed-slot unique index remains a separate database invariant. Six concurrent requests are regression evidence, not a capacity or production safety claim. See [verified results](hospital-milestone-1-verification.md).

# Clinical portal discovery v1

The portal uses the existing identity-v1, appointment-v1, clinical-linkage-v1, assessment-workflow-v1 and experimental-prediction APIs through the same-origin gateway. No separate browser identity or clinical role grant is created. All routes require a live booking bearer and fail closed on introspection/audit failure. Browser role navigation never replaces server policy.

## Discovery additions

`GET /api/v1/clinical/workspace` returns [workspace-v1](../clinical_api/contracts/workspace-v1.schema.json): source UUID plus at most 100 encounter references. A current approved patient link sees only that patient's APPROVED new assessment workflows. A current doctor/technician link sees only currently assigned new assessment encounters. Revoked links/assignments disappear. Legacy native clinical visits are not enumerated. Admin receives 403. Each disclosure has a committed clinical-read audit; audit failure returns 503 without payload.

`GET /api/v1/clinical/appointment-context/{appointmentUUID}` returns [appointment-context-v1](../clinical_api/contracts/appointment-context-v1.schema.json). A live mapped doctor must own the confirmed appointment according to the booking authority's existing owned appointment-v1 read. A second live session check and exact issuer/subject patient-link lookup resolve explicit patient/clinician mapping UUIDs; no name/email/patient-code matching occurs. Missing approved linkage is 409; wrong role is 403; cancelled appointment is 409; authority outage is 503. This is preparation only: existing assessment-request reservation/proof processing rechecks appointment status/ownership/mappings at creation, with existing retry/partial-failure handling. It grants no new clinician/technician assignment beyond that existing protocol.

`GET /api/v1/identity/staff` returns [staff-directory-v1](../booking-backend/contracts/staff-directory-v1.schema.json), admin-only, at most 100 staff, canonical doctor terminology. It exposes identity ID, name, email, role and lifecycle state only, never password/session/recovery material. Existing password-reauthenticated provisioning, role/revocation and security audit endpoints remain authoritative. Directory entries are not clinical links or assignments.

## Browser workflows

Clinical writes carry existing versioned UUID idempotency keys and optimistic expectedVersion. An uncertain response retains the exact command in memory for explicit retry; no new write proceeds until resolved. Definite rejection clears it. Reload discards memory; intake can recover its persisted request UUID from appointment state. Clinical reads and authenticated PNG fetches are never cached; Blob URLs are revoked after download/unmount. No public scan path or token URL is emitted.

Patient DTO validation rejects non-approved projections and extra human-history/notes/prediction fields. Only independent doctor approval produces the patient projection. Doctor model acknowledgement/dismissal remains in experimental prediction history; it never changes approval or copies scores into human findings. Approved findings remain immutable. New staff credentials require one-time private delivery and reset; generic public recovery does not disclose account state.

Lists currently have fixed caps without cursor pagination. There is no general linkage/assignment administration UI or emergency-intake UI; authorized existing emergency encounters remain visible/editable after explicit assignments. Synthetic operator commands are filesystem-only fixture controls, not production APIs or additional authorization mechanisms.

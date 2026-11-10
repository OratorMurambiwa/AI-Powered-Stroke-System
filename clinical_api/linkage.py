from uuid import uuid4
from .identity import IdentityAdapter
from .source import ClinicalSource
from .store import LinkStore, timestamp
from .validation import fields, uuid_id, subject_id, integer, ISSUER
from .errors import ClinicalError

class LinkOperator:
    """Trusted local operator boundary. Not mounted as an HTTP write API."""
    def __init__(self, store: LinkStore, source: ClinicalSource, identity: IdentityAdapter):
        self.store, self.source, self.identity = store, source, identity

    def register_person(self, command: dict, operator: str, reason: str) -> dict:
        fields(command, {"schemaVersion", "sourceId", "role", "recordId"})
        if uuid_id(command["sourceId"]) != self.source.source_id:
            raise ClinicalError(409, "source_mismatch")
        role = command["role"]
        if not isinstance(role, str) or role not in {"patient", "doctor", "technician"}:
            raise ClinicalError(400, "invalid_clinical_role")
        native_id = integer(command["recordId"], 1)
        person_id = self.source.check_person(role, native_id)
        with self.store.connection(write=True) as db:
            db.execute("INSERT INTO people VALUES(?,?,?,?,?)", (person_id, self.source.source_id, role, native_id, timestamp()))
            self.store.audit(db, "PERSON_REGISTERED", person_id, operator, reason)
        return {"schemaVersion": 1, "personId": person_id, "role": role, "sourceId": self.source.source_id}

    def register_encounter(self, command: dict, operator: str, reason: str) -> dict:
        fields(command, {"schemaVersion", "sourceId", "patientId", "recordId"})
        if uuid_id(command["sourceId"]) != self.source.source_id:
            raise ClinicalError(409, "source_mismatch")
        patient_id = uuid_id(command["patientId"])
        native_id = integer(command["recordId"], 1)
        with self.store.connection(write=True) as db:
            patient = db.execute("SELECT * FROM people WHERE id=? AND kind='patient'", (patient_id,)).fetchone()
            if not patient:
                raise ClinicalError(404, "clinical_record_not_found")
            encounter_id = self.source.check_encounter(native_id, patient["native_id"])
            db.execute("INSERT INTO encounters(id,patient_id,source_id,native_id,created_at) VALUES(?,?,?,?,?)", (encounter_id, patient_id, self.source.source_id, native_id, timestamp()))
            self.store.audit(db, "ENCOUNTER_REGISTERED", encounter_id, operator, reason)
        return {"schemaVersion": 1, "encounterId": encounter_id, "patientId": patient_id}

    def link(self, command: dict, bearer: str, operator: str, reason: str) -> dict:
        fields(command, {"schemaVersion", "issuer", "subject", "role", "personId"})
        person_id = uuid_id(command["personId"])
        subject_id(command["subject"])
        principal = self.identity.introspect(bearer)
        if command["issuer"] != ISSUER or principal.subject != command["subject"] or principal.role != command["role"]:
            raise ClinicalError(409, "identity_proof_mismatch")
        if principal.role not in {"patient", "doctor", "technician"}:
            raise ClinicalError(403, "clinical_access_forbidden")
        link_id = str(uuid4())
        created = timestamp()
        with self.store.connection(write=True) as db:
            person = db.execute("SELECT * FROM people WHERE id=?", (person_id,)).fetchone()
            if not person or person["kind"] != principal.role:
                raise ClinicalError(409, "clinical_role_mismatch")
            if self.source.check_person(principal.role, person["native_id"]) != person_id:
                raise ClinicalError(409, "record_identity_mismatch")
            db.execute("INSERT INTO identity_links VALUES(?,?,?,?,?,?,?,?,NULL)", (
                link_id, 1, ISSUER, principal.subject, person_id, principal.role, principal.role_version, created))
            self.store.audit(db, "IDENTITY_LINKED", link_id, operator, reason)
        return {"schemaVersion": 1, "mappingId": link_id, "issuer": ISSUER, "subject": principal.subject,
                "personId": person_id, "role": principal.role, "roleVersion": principal.role_version,
                "sourceId": self.source.source_id, "createdAt": created}

    def assign(self, command: dict, bearer: str, operator: str, reason: str) -> dict:
        fields(command, {"schemaVersion", "mappingId", "encounterId"})
        mapping_id, encounter_id = uuid_id(command["mappingId"]), uuid_id(command["encounterId"])
        principal = self.identity.introspect(bearer)
        if principal.role not in {"doctor", "technician"}:
            raise ClinicalError(403, "clinical_access_forbidden")
        assignment_id = str(uuid4())
        with self.store.connection(write=True) as db:
            link = db.execute("SELECT * FROM identity_links WHERE id=? AND revoked_at IS NULL", (mapping_id,)).fetchone()
            if (not link or link["subject"] != principal.subject or link["role"] != principal.role
                    or link["role_version"] != principal.role_version or link["issuer"] != principal.issuer):
                raise ClinicalError(409, "identity_proof_mismatch")
            if not db.execute("SELECT id FROM encounters WHERE id=?", (encounter_id,)).fetchone():
                raise ClinicalError(404, "clinical_record_not_found")
            db.execute("INSERT INTO assignments VALUES(?,?,?,?,NULL)", (assignment_id, mapping_id, encounter_id, timestamp()))
            self.store.audit(db, "ENCOUNTER_ASSIGNED", assignment_id, operator, reason)
        return {"schemaVersion": 1, "assignmentId": assignment_id, "mappingId": mapping_id, "encounterId": encounter_id}

    def revoke(self, command: dict, operator: str, reason: str, *, assignment: bool = False) -> None:
        fields(command, {"schemaVersion", "id"})
        record_id = uuid_id(command["id"])
        table = "assignments" if assignment else "identity_links"  # Fixed identifiers, never user SQL.
        with self.store.connection(write=True) as db:
            result = db.execute(f"UPDATE {table} SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (timestamp(), record_id))
            if result.rowcount != 1:
                raise ClinicalError(409, "mapping_not_active")
            self.store.audit(db, "ASSIGNMENT_REVOKED" if assignment else "LINK_REVOKED", record_id, operator, reason)

    def grant_intake(self, command: dict, bearer: str, operator: str, reason: str) -> dict:
        import time
        fields(command, {"schemaVersion", "mappingId", "patientId", "expiresAt"})
        if self.store.version != 2:
            raise ClinicalError(503, "assessment_store_v2_required")
        mapping_id, patient_id = uuid_id(command["mappingId"]), uuid_id(command["patientId"])
        expiry = integer(command["expiresAt"])
        if not time.time() + 60 <= expiry <= time.time() + 86400:
            raise ClinicalError(400, "invalid_intake_expiration")
        principal = self.identity.introspect(bearer)
        if principal.role not in {"doctor", "technician"}:
            raise ClinicalError(403, "clinical_access_forbidden")
        grant_id = str(uuid4())
        with self.store.connection(write=True) as db:
            link = db.execute("SELECT * FROM identity_links WHERE id=? AND revoked_at IS NULL", (mapping_id,)).fetchone()
            patient = db.execute("SELECT * FROM people WHERE id=? AND kind='patient'", (patient_id,)).fetchone()
            if not link or link["subject"] != principal.subject or link["role"] != principal.role or link["role_version"] != principal.role_version:
                raise ClinicalError(409, "identity_proof_mismatch")
            if not patient or self.source.check_person('patient', patient['native_id']) != patient_id:
                raise ClinicalError(409, "record_identity_mismatch")
            db.execute("INSERT INTO intake_grants VALUES(?,?,?,?,?,NULL)", (grant_id, mapping_id, patient_id, expiry, timestamp()))
            self.store.audit(db, "INTAKE_GRANTED", grant_id, operator, reason)
        return {"schemaVersion": 1, "intakeGrantId": grant_id, "mappingId": mapping_id, "patientId": patient_id, "expiresAt": expiry}

    def revoke_intake(self, command: dict, operator: str, reason: str) -> None:
        fields(command, {"schemaVersion", "id"})
        grant_id = uuid_id(command["id"])
        if self.store.version != 2:
            raise ClinicalError(503, "assessment_store_v2_required")
        with self.store.connection(write=True) as db:
            result = db.execute("UPDATE intake_grants SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (timestamp(), grant_id))
            if result.rowcount != 1:
                raise ClinicalError(409, "intake_grant_not_active")
            self.store.audit(db, "INTAKE_REVOKED", grant_id, operator, reason)

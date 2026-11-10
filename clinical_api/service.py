import time
from .identity import IdentityAdapter, Principal
from .source import ClinicalSource
from .store import LinkStore
from .validation import uuid_id
from .errors import ClinicalError

class ClinicalService:
    def __init__(self, identity: IdentityAdapter, store: LinkStore, source: ClinicalSource):
        self.identity, self.store, self.source = identity, store, source

    def _link(self, db, principal: Principal):
        if principal.role == "admin":
            raise ClinicalError(403, "clinical_access_forbidden")
        if time.time() >= principal.expires_at:
            raise ClinicalError(401, "invalid_session")
        link = db.execute("SELECT * FROM identity_links WHERE issuer=? AND subject=? AND revoked_at IS NULL",
                          (principal.issuer, principal.subject)).fetchone()
        if not link or link["role"] != principal.role or link["role_version"] != principal.role_version:
            raise ClinicalError(403, "clinical_link_required")
        person = db.execute("SELECT * FROM people WHERE id=?", (link["person_id"],)).fetchone()
        if not person or person["kind"] != principal.role or self.source.check_person(principal.role, person["native_id"]) != person["id"]:
            raise ClinicalError(503, "record_identity_mismatch")
        return link

    def patient(self, bearer: str | None, patient_id: str, *, encounters: bool = False) -> dict:
        principal = self.identity.introspect(bearer)
        patient_id = uuid_id(patient_id)
        with self.store.connection() as db:
            link = self._link(db, principal)
            if principal.role != "patient":
                raise ClinicalError(403, "encounter_assignment_required")
            if link["person_id"] != patient_id:
                raise ClinicalError(404, "clinical_record_not_found")
            patient = db.execute("SELECT * FROM people WHERE id=? AND kind='patient'", (patient_id,)).fetchone()
            if not patient:
                raise ClinicalError(404, "clinical_record_not_found")
            if encounters:
                rows = db.execute("SELECT id FROM encounters WHERE patient_id=? ORDER BY id LIMIT 100", (patient_id,)).fetchall()
                return {"schemaVersion": 1, "patientId": patient_id, "encounters": [{"encounterId": row["id"]} for row in rows]}
            return {"schemaVersion": 1, "patientId": patient_id, "demographics": self.source.patient(patient["native_id"], patient_id)}

    def encounter(self, bearer: str | None, encounter_id: str) -> dict:
        principal = self.identity.introspect(bearer)
        encounter_id = uuid_id(encounter_id)
        with self.store.connection() as db:
            link = self._link(db, principal)
            encounter = db.execute("SELECT * FROM encounters WHERE id=?", (encounter_id,)).fetchone()
            if not encounter:
                raise ClinicalError(404, "clinical_record_not_found")
            if principal.role == "patient":
                allowed = link["person_id"] == encounter["patient_id"]
            else:
                allowed = db.execute("SELECT id FROM assignments WHERE link_id=? AND encounter_id=? AND revoked_at IS NULL",
                                     (link["id"], encounter_id)).fetchone() is not None
            if not allowed:
                raise ClinicalError(404, "clinical_record_not_found")
            person = db.execute("SELECT * FROM people WHERE id=? AND kind='patient'", (encounter["patient_id"],)).fetchone()
            if not person:
                raise ClinicalError(503, "clinical_record_unavailable")
            detail = self.source.encounter(encounter["native_id"], person["native_id"], encounter_id, person["id"])
            return {"schemaVersion": 1, "encounterId": encounter_id, "patientId": person["id"],
                    "encounter": detail, "experimental": True, "clinicianReviewRequired": True}

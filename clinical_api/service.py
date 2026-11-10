import time
import json
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

    def _audited(self, bearer: str | None, identifier: str, kind: str, read) -> dict:
        principal = None
        failure = None
        target = "invalid"
        result = None
        try:
            target = uuid_id(identifier)
            principal = self.identity.introspect(bearer)
        except ClinicalError as error:
            failure = error
        try:
            with self.store.connection(write=True) as db:
                if failure is None:
                    try:
                        result = read(db, principal, target)
                    except ClinicalError as error:
                        failure = error
                outcome = "allowed" if failure is None else "denied" if failure.status < 500 else "failed"
                reason = json.dumps({"schemaVersion": 1, "sessionId": principal.session_id if principal else None,
                                     "role": principal.role if principal else None, "resourceKind": kind,
                                     "outcome": outcome, "status": failure.status if failure else 200,
                                     "errorCode": failure.code if failure else None}, separators=(",", ":"))
                self.store.audit(db, "CLINICAL_READ", target, principal.subject if principal else "unauthenticated", reason)
        except ClinicalError:
            # No clinical payload may be disclosed without a committed read audit.
            raise ClinicalError(503, "clinical_audit_unavailable") from None
        if failure:
            raise failure
        return result

    def patient(self, bearer: str | None, patient_id: str, *, encounters: bool = False) -> dict:
        def read(db, principal, target):
            link = self._link(db, principal)
            if principal.role != "patient":
                raise ClinicalError(403, "encounter_assignment_required")
            if link["person_id"] != target:
                raise ClinicalError(404, "clinical_record_not_found")
            patient = db.execute("SELECT * FROM people WHERE id=? AND kind='patient'", (target,)).fetchone()
            if not patient:
                raise ClinicalError(404, "clinical_record_not_found")
            if encounters:
                rows = db.execute("SELECT id FROM encounters WHERE patient_id=? ORDER BY id LIMIT 100", (target,)).fetchall()
                return {"schemaVersion": 1, "patientId": target, "encounters": [{"encounterId": row["id"]} for row in rows]}
            return {"schemaVersion": 1, "patientId": target, "demographics": self.source.patient(patient["native_id"], target)}
        return self._audited(bearer, patient_id, "patient_encounters" if encounters else "patient", read)

    def encounter(self, bearer: str | None, encounter_id: str) -> dict:
        def read(db, principal, target):
            link = self._link(db, principal)
            encounter = db.execute("SELECT * FROM encounters WHERE id=?", (target,)).fetchone()
            if not encounter:
                raise ClinicalError(404, "clinical_record_not_found")
            if principal.role == "patient":
                allowed = link["person_id"] == encounter["patient_id"]
            else:
                allowed = db.execute("SELECT id FROM assignments WHERE link_id=? AND encounter_id=? AND revoked_at IS NULL",
                                     (link["id"], target)).fetchone() is not None
            if not allowed:
                raise ClinicalError(404, "clinical_record_not_found")
            person = db.execute("SELECT * FROM people WHERE id=? AND kind='patient'", (encounter["patient_id"],)).fetchone()
            if not person:
                raise ClinicalError(503, "clinical_record_unavailable")
            if encounter["native_id"] is None:
                row = db.execute("SELECT mode,appointment_id,status,reason_code,created_at FROM assessment_records WHERE id=?", (target,)).fetchone()
                if not row:
                    raise ClinicalError(503, "clinical_record_unavailable")
                detail = {"mode": row['mode'], "appointmentId": row['appointment_id'], "status": row['status'], "reasonCode": row['reason_code'], "createdAt": row['created_at']}
            else:
                detail = self.source.encounter(encounter["native_id"], person["native_id"], target, person["id"])
            return {"schemaVersion": 1, "encounterId": target, "patientId": person["id"],
                    "encounter": detail, "experimental": True, "clinicianReviewRequired": True}
        return self._audited(bearer, encounter_id, "encounter", read)

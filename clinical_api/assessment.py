import hashlib
import json
import time
from uuid import uuid4, uuid5, UUID
from .booking import BookingAdapter
from .errors import ClinicalError
from .service import ClinicalService
from .store import timestamp
from .validation import ISSUER, fields, uuid_id

class AssessmentService:
    def __init__(self, clinical: ClinicalService):
        self.clinical = clinical
        self.store, self.source, self.identity = clinical.store, clinical.source, clinical.identity
        self.booking = BookingAdapter(self.identity)

    @staticmethod
    def digest(values: list) -> str:
        return hashlib.sha256(json.dumps(values, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()

    def _mapped(self, db, mapping_id: str, role: str, person_id: str | None = None, subject: str | None = None, epoch: int | None = None):
        link = db.execute('SELECT * FROM identity_links WHERE id=? AND revoked_at IS NULL', (mapping_id,)).fetchone()
        if (not link or link['issuer'] != ISSUER or link['role'] != role or (person_id is not None and link['person_id'] != person_id)
                or (subject is not None and link['subject'] != subject) or (epoch is not None and link['role_version'] != epoch)):
            raise ClinicalError(409, 'clinical_mapping_mismatch')
        person = db.execute('SELECT * FROM people WHERE id=? AND kind=?', (link['person_id'], role)).fetchone()
        if not person or self.source.check_person(role, person['native_id']) != person['id']:
            raise ClinicalError(503, 'record_identity_mismatch')
        return link

    def scheduled(self, bearer: str, command: dict) -> dict:
        if self.store.version < 2:
            raise ClinicalError(503, 'assessment_store_v2_required')
        fields(command, {'schemaVersion','mode','requestId','appointmentId','encounterId','sourceId','patientId','patientMappingId','clinicianMappingId'})
        if command['mode'] != 'SCHEDULED':
            raise ClinicalError(400, 'invalid_assessment_mode')
        for key in ('requestId','appointmentId','encounterId','sourceId','patientId','patientMappingId','clinicianMappingId'):
            uuid_id(command[key])
        actor = self.identity.introspect(bearer)
        if actor.role != 'doctor':
            raise ClinicalError(403, 'assigned_doctor_required')
        digest = self.digest([1,'SCHEDULED',command['requestId'],command['appointmentId'],command['encounterId'],command['sourceId'],command['patientId'],command['patientMappingId'],command['clinicianMappingId']])
        proof = self.booking.proof(bearer, actor, command['appointmentId'], command['requestId'], digest, command['encounterId'])
        with self.store.connection(write=True) as db:
            if time.time() >= actor.expires_at:
                raise ClinicalError(401, 'invalid_session')
            previous = self._previous(db, command['requestId'], digest, actor.subject)
            if previous:
                return previous
            failure = None
            try:
                if command['sourceId'] != self.source.source_id:
                    raise ClinicalError(409, 'clinical_source_mismatch')
                self._mapped(db, command['patientMappingId'], 'patient', command['patientId'], proof['patientSubject'], proof['patientRoleVersion'])
                clinician = self._mapped(db, command['clinicianMappingId'], 'doctor', subject=proof['doctorSubject'], epoch=proof['doctorRoleVersion'])
            except ClinicalError as error:
                if error.status >= 500:
                    raise
                failure = error.code
            receipt = self._receipt(command, 'REJECTED' if failure else 'CREATED', failure)
            if not failure:
                self._create(db, command, clinician['id'], clinician['id'], None)
            self._save(db, command, digest, actor.subject, receipt)
            self.store.audit(db, 'ASSESSMENT_REJECTED' if failure else 'ASSESSMENT_CREATED', command['encounterId'], actor.subject, failure or 'confirmed_appointment')
            return receipt

    def emergency(self, bearer: str, command: dict) -> dict:
        if self.store.version < 2:
            raise ClinicalError(503, 'assessment_store_v2_required')
        fields(command, {'schemaVersion','requestId','sourceId','patientId','patientMappingId','actorMappingId','intakeGrantId','reasonCode'})
        for key in ('requestId','sourceId','patientId','patientMappingId','actorMappingId','intakeGrantId'):
            uuid_id(command[key])
        if not isinstance(command['reasonCode'], str) or command['reasonCode'] not in {'SUSPECTED_STROKE','URGENT_REASSESSMENT'}:
            raise ClinicalError(400, 'invalid_emergency_reason')
        actor = self.identity.introspect(bearer)
        if actor.role not in {'doctor','technician'}:
            raise ClinicalError(403, 'clinical_access_forbidden')
        digest = self.digest([1,'EMERGENCY',command['requestId'],command['sourceId'],command['patientId'],command['patientMappingId'],command['actorMappingId'],command['intakeGrantId'],command['reasonCode']])
        with self.store.connection(write=True) as db:
            link = self.clinical._link(db, actor)
            if link['id'] != command['actorMappingId'] or command['sourceId'] != self.source.source_id:
                raise ClinicalError(409, 'clinical_mapping_mismatch')
            previous = self._previous(db, command['requestId'], digest, actor.subject)
            if previous:
                return previous
            self._mapped(db, command['patientMappingId'], 'patient', command['patientId'])
            grant = db.execute('SELECT * FROM intake_grants WHERE id=? AND revoked_at IS NULL', (command['intakeGrantId'],)).fetchone()
            if not grant or grant['link_id'] != link['id'] or grant['patient_id'] != command['patientId'] or grant['expires_at'] <= time.time():
                raise ClinicalError(403, 'patient_intake_grant_required')
            values = {**command, 'mode': 'EMERGENCY', 'appointmentId': None, 'encounterId': str(uuid5(UUID(self.source.source_id), 'emergency:' + command['requestId'])), 'clinicianMappingId': link['id']}
            self._create(db, values, link['id'], link['id'], command['reasonCode'])
            receipt = self._receipt(values, 'CREATED', None)
            self._save(db, values, digest, actor.subject, receipt)
            self.store.audit(db, 'EMERGENCY_ASSESSMENT_CREATED', values['encounterId'], actor.subject, command['reasonCode'])
            return receipt

    @staticmethod
    def _previous(db, request_id: str, digest: str, actor_subject: str):
        row = db.execute('SELECT * FROM assessment_receipts WHERE request_id=?', (request_id,)).fetchone()
        if row:
            if row['request_hash'] != digest or row['actor_subject'] != actor_subject:
                raise ClinicalError(409, 'idempotency_conflict')
            return json.loads(row['receipt'])
        return None

    @staticmethod
    def _receipt(command: dict, state: str, error: str | None) -> dict:
        return {key: command[key] for key in ('schemaVersion','mode','requestId','appointmentId','encounterId','sourceId','patientId','clinicianMappingId')} | {'state': state, 'errorCode': error}

    def _create(self, db, command: dict, actor_link: str, clinician_link: str, reason: str | None) -> None:
        created = timestamp()
        db.execute('INSERT INTO encounters(id,patient_id,source_id,native_id,created_at) VALUES(?,?,?,NULL,?)', (command['encounterId'],command['patientId'],self.source.source_id,created))
        db.execute('INSERT INTO assessment_records VALUES(?,?,?,?,?,?,?,?)', (command['encounterId'],command['mode'],command['appointmentId'],actor_link,clinician_link,reason,'ASSESSMENT_PENDING',created))
        db.execute('INSERT INTO assignments VALUES(?,?,?,?,NULL)', (str(uuid4()),clinician_link,command['encounterId'],created))

    @staticmethod
    def _save(db, command: dict, digest: str, actor: str, receipt: dict) -> None:
        db.execute('INSERT INTO assessment_receipts VALUES(?,?,?,?,?,?,?,?)', (command['requestId'],digest,actor,command['encounterId'],command['appointmentId'],receipt['state'],json.dumps(receipt,separators=(',',':')),timestamp()))

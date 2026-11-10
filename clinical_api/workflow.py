"""Human observations/review only. No inference or treatment execution."""
import base64
import binascii
import hashlib
import json
import math
from uuid import uuid4
from .errors import ClinicalError
from .png import validate_png, MAX_SCAN
from .store import timestamp
from .validation import fields, text, uuid_id

NIHSS_MAX = {'consciousness':3, 'questions':2, 'commands':2, 'gaze':2, 'visual':3,
             'facial':3, 'leftArm':4, 'rightArm':4, 'leftLeg':4, 'rightLeg':4,
             'ataxia':2, 'sensory':2, 'language':3, 'dysarthria':2, 'neglect':2}
VITALS = {'systolicMmHg':(20,300), 'diastolicMmHg':(10,200), 'pulseBpm':(10,300),
          'temperatureC':(25,45), 'oxygenPercent':(0,100), 'glucoseMgDl':(10,1000)}

class ReviewWorkflow:
    def __init__(self, clinical):
        self.clinical, self.store = clinical, clinical.store

    def _access(self, db, actor, encounter_id, *, staff=False):
        link = self.clinical._link(db, actor)
        encounter = db.execute('SELECT * FROM assessment_records WHERE id=?', (encounter_id,)).fetchone()
        if not encounter:
            raise ClinicalError(404, 'assessment_not_found')
        patient = db.execute('SELECT patient_id FROM encounters WHERE id=?', (encounter_id,)).fetchone()[0]
        if actor.role == 'patient':
            if staff or link['person_id'] != patient:
                raise ClinicalError(404, 'assessment_not_found')
        elif actor.role not in {'doctor','technician'} or not db.execute(
                'SELECT id FROM assignments WHERE link_id=? AND encounter_id=? AND revoked_at IS NULL',
                (link['id'],encounter_id)).fetchone():
            raise ClinicalError(404, 'assessment_not_found')
        return link

    @staticmethod
    def _current(db, encounter_id):
        row = db.execute('SELECT * FROM assessment_workflows WHERE encounter_id=?', (encounter_id,)).fetchone()
        return dict(row) if row else {'version':0,'state':'DRAFT','document':'{"vitals":null,"nihss":null,"notes":[],"scans":[]}',
                                      'approved_summary':None,'reviewed_by':None,'reviewed_at':None}

    def read(self, bearer, encounter_id):
        def read(db, actor, target):
            self._access(db, actor, target)
            row = self._current(db, target)
            if actor.role == 'patient' and row['state'] != 'APPROVED':
                raise ClinicalError(404, 'approved_result_not_found')
            result = {'schemaVersion':1,'encounterId':target,'version':row['version'],'state':row['state'],
                      'experimental':True,'inferencePerformed':False,'clinicianReviewRequired':True,
                      'summary':row['approved_summary'],'reviewedBy':row['reviewed_by'],'reviewedAt':row['reviewed_at']}
            document = json.loads(row['document'])
            if actor.role == 'patient':
                # Internal notes and rejected/draft history never enter patient projections.
                result['observations'] = {k:document[k] for k in ('vitals','nihss','scans','observedAt')}
            else:
                result['observations'] = document
                result['history'] = [json.loads(r['provenance']) | {'action':r['action'],'version':r['version'],
                                     'snapshot':json.loads(r['snapshot'])}
                                     for r in db.execute('SELECT * FROM assessment_changes WHERE encounter_id=? ORDER BY version', (target,))]
            return result
        return self.clinical._audited(bearer, encounter_id, 'assessment', read)

    def scan(self, bearer, encounter_id, scan_id):
        uuid_id(scan_id)
        def read(db, actor, target):
            self._access(db, actor, target)
            row = self._current(db, target)
            if actor.role == 'patient' and row['state'] != 'APPROVED':
                raise ClinicalError(404, 'approved_result_not_found')
            scan = db.execute('SELECT content,sha256,size FROM assessment_scans WHERE id=? AND encounter_id=?', (scan_id,target)).fetchone()
            if not scan:
                raise ClinicalError(404, 'scan_not_found')
            raw = bytes(scan['content'])
            if len(raw) != scan['size'] or hashlib.sha256(raw).hexdigest() != scan['sha256']:
                raise ClinicalError(503, 'scan_integrity_failure')
            return raw
        return self.clinical._audited(bearer, encounter_id, 'scan:' + scan_id, read)

    def mutate(self, bearer, encounter_id, command):
        def operation(db, actor, target):
            link = self._access(db, actor, target, staff=True)
            # Savepoint keeps denied mutation attempts auditable without partial writes.
            db.execute('SAVEPOINT assessment_action')
            try:
                result = self._change(db, actor, link, target, command)
            except ClinicalError:
                db.execute('ROLLBACK TO assessment_action')
                db.execute('RELEASE assessment_action')
                raise
            db.execute('RELEASE assessment_action')
            return result
        return self.clinical._audited(bearer, encounter_id, 'assessment_mutation', operation, audit_action='ASSESSMENT_ACCESS')

    def _change(self, db, actor, link, encounter_id, command):
        fields(command, {'schemaVersion','requestId','expectedVersion','action','data'})
        request_id = uuid_id(command['requestId'])
        if type(command['expectedVersion']) is not int or command['expectedVersion'] < 0:
            raise ClinicalError(400, 'invalid_expected_version')
        action, data = command['action'], command['data']
        if not isinstance(action,str) or action not in {'OBSERVATIONS','SCAN','NOTE','SUBMIT','APPROVE','REJECT'} or not isinstance(data,dict):
            raise ClinicalError(400, 'invalid_assessment_action')
        if action in {'NOTE','APPROVE','REJECT'} and actor.role != 'doctor':
            raise ClinicalError(403, 'assigned_doctor_required')
        digest = hashlib.sha256(json.dumps(command,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        previous = db.execute('SELECT * FROM assessment_changes WHERE request_id=?', (request_id,)).fetchone()
        if previous:
            if previous['encounter_id'] != encounter_id or previous['actor_subject'] != actor.subject or previous['request_hash'] != digest:
                raise ClinicalError(409, 'idempotency_conflict')
            return json.loads(previous['receipt'])
        row = self._current(db, encounter_id)
        if row['version'] != command['expectedVersion']:
            raise ClinicalError(409, 'assessment_version_conflict')
        if row['version'] >= 128:
            raise ClinicalError(409, 'assessment_history_limit')
        if row['state'] == 'APPROVED':
            raise ClinicalError(409, 'approved_assessment_immutable')
        document = json.loads(row['document'])
        version, state, scan_id = row['version']+1, row['state'], None
        now = timestamp()
        summary, reviewed_by, reviewed_at = None, None, None
        if action in {'OBSERVATIONS','SCAN','NOTE'}:
            if state == 'SUBMITTED':
                raise ClinicalError(409, 'assessment_under_review')
            state = 'DRAFT'
            if action == 'OBSERVATIONS':
                if set(data) != {'vitals','nihss','observedAt'} or not isinstance(data['vitals'],dict) or not isinstance(data['nihss'],dict):
                    raise ClinicalError(400, 'invalid_observations')
                from datetime import datetime, timezone
                try:
                    observed = datetime.fromisoformat(data['observedAt'])
                    if observed.tzinfo is None or observed.utcoffset().total_seconds() != 0 or observed > datetime.now(timezone.utc):
                        raise ValueError
                except (ValueError,TypeError,AttributeError):
                    raise ClinicalError(400, 'invalid_observation_time') from None
                if set(data['vitals']) != set(VITALS) or set(data['nihss']) != set(NIHSS_MAX):
                    raise ClinicalError(400, 'incomplete_observations')
                for key,(low,high) in VITALS.items():
                    value = data['vitals'][key]
                    if type(value) not in {int,float} or not math.isfinite(value) or not low <= value <= high:
                        raise ClinicalError(400, 'invalid_vital')
                if data['vitals']['diastolicMmHg'] >= data['vitals']['systolicMmHg']:
                    raise ClinicalError(400, 'invalid_blood_pressure')
                for key,maximum in NIHSS_MAX.items():
                    if type(data['nihss'][key]) is not int or not 0 <= data['nihss'][key] <= maximum:
                        raise ClinicalError(400, 'invalid_nihss_observation')
                document['vitals'], document['nihss'] = data['vitals'], data['nihss']
                document['observedAt'] = observed.isoformat()
            elif action == 'NOTE':
                if set(data) != {'text'} or len(document['notes']) >= 16:
                    raise ClinicalError(400, 'invalid_note')
                document['notes'].append({'text':text(data['text'],2000),'subject':actor.subject,'at':now})
            else:
                if set(data) != {'mediaType','contentBase64'} or data['mediaType'] != 'image/png' or not isinstance(data['contentBase64'],str):
                    raise ClinicalError(400, 'invalid_scan_contract')
                if len(data['contentBase64']) > 4*((MAX_SCAN+2)//3):
                    raise ClinicalError(413, 'scan_too_large')
                if len(document['scans']) >= 16:
                    raise ClinicalError(409, 'scan_limit')
                try:
                    raw = base64.b64decode(data['contentBase64'],validate=True)
                except (ValueError,binascii.Error):
                    raise ClinicalError(400, 'invalid_scan_encoding') from None
                validate_png(raw)
                scan_id, sha = str(uuid4()), hashlib.sha256(raw).hexdigest()
                db.execute('INSERT INTO assessment_scans VALUES(?,?,?,?,?,?,?,?,?)', (scan_id,encounter_id,sha,'image/png',len(raw),raw,version,now,actor.subject))
                document['scans'].append({'scanId':scan_id,'sha256':sha,'mediaType':'image/png','size':len(raw)})
        elif action == 'SUBMIT':
            if data or state not in {'DRAFT','REJECTED'}:
                raise ClinicalError(409, 'invalid_assessment_transition')
            if not document['vitals'] or not document['nihss'] or not document['scans']:
                raise ClinicalError(409, 'assessment_incomplete')
            state = 'SUBMITTED'
        else:
            if state != 'SUBMITTED':
                raise ClinicalError(409, 'assessment_not_submitted')
            if set(data) != {'summary','attested'} or data['attested'] is not True:
                raise ClinicalError(400, 'clinician_attestation_required')
            summary, reviewed_by, reviewed_at = text(data['summary'],4000), actor.subject, now
            state = 'APPROVED' if action == 'APPROVE' else 'REJECTED'
        payload = json.dumps(document,separators=(',',':'),allow_nan=False)
        db.execute('INSERT INTO assessment_workflows VALUES(?,?,?,?,?,?,?) ON CONFLICT(encounter_id) DO UPDATE SET version=excluded.version,state=excluded.state,document=excluded.document,approved_summary=excluded.approved_summary,reviewed_by=excluded.reviewed_by,reviewed_at=excluded.reviewed_at',
                   (encounter_id,version,state,payload,summary,reviewed_by,reviewed_at))
        receipt = {'schemaVersion':1,'requestId':request_id,'encounterId':encounter_id,'version':version,'state':state,'scanId':scan_id}
        provenance = {'schemaVersion':1,'subject':actor.subject,'mappingId':link['id'],'role':actor.role,
                      'roleVersion':actor.role_version,'sessionId':actor.session_id,'at':now,'inputSha256':digest,
                      'experimental':True,'inferencePerformed':False,'summary':summary}
        db.execute('INSERT INTO assessment_changes VALUES(?,?,?,?,?,?,?,?,?,?)', (request_id,encounter_id,actor.subject,digest,version,action,now,json.dumps(provenance),payload,json.dumps(receipt)))
        self.store.audit(db,'ASSESSMENT_'+action,encounter_id,actor.subject,json.dumps({'schemaVersion':1,'requestId':request_id,'version':version,'mappingId':link['id']}))
        return receipt

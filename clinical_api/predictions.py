"""Independent experimental records; never edits observations or approved findings."""
import hashlib
import json
import time
from uuid import uuid4
from .errors import ClinicalError
from .inference import MODEL_SHA256
from .store import timestamp
from .validation import fields, uuid_id, text
from .workflow import ReviewWorkflow

class PredictionService:
    def __init__(self,clinical):
        self.clinical,self.store=clinical,clinical.store
        self.workflow=ReviewWorkflow(clinical)

    def _doctor(self,db,actor,target):
        if actor.role!='doctor':
            raise ClinicalError(403,'assigned_doctor_required')
        return self.workflow._access(db,actor,target,staff=True)

    @staticmethod
    def _view(row):
        return {'schemaVersion':1,'requestId':row['request_id'],'predictionId':row['prediction_id'],
                'encounterId':row['encounter_id'],'scanId':row['scan_id'],'state':row['state'],
                'attempts':row['attempts'],'errorCode':row['error_code'],
                'prediction':json.loads(row['result']) if row['result'] else None,
                'experimental':True,'clinicianReviewRequired':True,'patientVisible':False}

    def create(self,bearer,encounter_id,command):
        fields(command,{'schemaVersion','requestId','scanId'})
        request_id,scan_id=uuid_id(command['requestId']),uuid_id(command['scanId'])
        digest=hashlib.sha256(json.dumps([1,encounter_id,scan_id,MODEL_SHA256],separators=(',',':')).encode()).hexdigest()
        work={}
        def reserve(db,actor,target):
            link=self._doctor(db,actor,target)
            if not getattr(self.clinical,'inference',None):
                raise ClinicalError(503,'inference_not_configured')
            scan=db.execute('SELECT * FROM assessment_scans WHERE id=? AND encounter_id=?',(scan_id,target)).fetchone()
            if not scan:
                raise ClinicalError(404,'scan_not_found')
            raw=bytes(scan['content'])
            if len(raw)!=scan['size'] or hashlib.sha256(raw).hexdigest()!=scan['sha256']:
                raise ClinicalError(503,'scan_integrity_failure')
            row=db.execute('SELECT * FROM prediction_jobs WHERE request_id=?',(request_id,)).fetchone()
            if row:
                if row['request_hash']!=digest or row['actor_subject']!=actor.subject or row['actor_mapping']!=link['id']:
                    raise ClinicalError(409,'idempotency_conflict')
                if row['state']=='SUCCEEDED' or (row['state']=='PENDING' and row['lease_until']>time.time()):
                    return self._view(row)
                if row['attempts']>=3:
                    raise ClinicalError(409,'inference_retry_limit')
            else:
                if db.execute('SELECT count(*) FROM prediction_jobs WHERE encounter_id=?',(target,)).fetchone()[0]>=16:
                    raise ClinicalError(409,'prediction_limit')
                now=timestamp()
                db.execute('INSERT INTO prediction_jobs(request_id,prediction_id,encounter_id,scan_id,actor_subject,actor_mapping,request_hash,state,attempts,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                           (request_id,str(uuid4()),target,scan_id,actor.subject,link['id'],digest,'FAILED',0,now,now))
            lease=str(uuid4())
            db.execute("UPDATE prediction_jobs SET state='PENDING',attempts=attempts+1,lease_token=?,lease_until=?,updated_at=?,error_code=NULL WHERE request_id=?",
                       (lease,time.time()+35,timestamp(),request_id))
            work.update(raw=raw,sha=scan['sha256'],lease=lease,subject=actor.subject,mapping=link['id'])
            row=db.execute('SELECT * FROM prediction_jobs WHERE request_id=?',(request_id,)).fetchone()
            self.store.audit(db,'PREDICTION_RESERVED',row['prediction_id'],actor.subject,json.dumps({'requestId':request_id,'attempt':row['attempts']}))
            return self._view(row)
        result=self.clinical._audited(bearer,encounter_id,'prediction_request',reserve,audit_action='PREDICTION_ACCESS')
        if not work:
            return result
        try:
            # No SQLite transaction or session token is held by the worker.
            prediction=self.clinical.inference.predict(work['raw'],work['sha'])
            actor=self.clinical.identity.introspect(bearer)
            with self.store.connection(write=True) as db:
                link=self._doctor(db,actor,encounter_id)
                if actor.subject!=work['subject'] or link['id']!=work['mapping']:
                    raise ClinicalError(403,'clinical_link_required')
                row=db.execute('SELECT * FROM prediction_jobs WHERE request_id=?',(request_id,)).fetchone()
                if row['lease_token']!=work['lease'] or row['state']!='PENDING' or row['lease_until']<=time.time():
                    raise ClinicalError(409,'inference_lease_conflict')
                record={'schemaVersion':1,'predictionId':row['prediction_id'],'encounterId':encounter_id,'scanId':scan_id,
                        'requestedAt':row['created_at'],'completedAt':timestamp(),'requestedBy':actor.subject,
                        'mappingId':link['id'],'roleVersion':actor.role_version,**prediction,
                        'experimental':True,'clinicianReviewRequired':True,'patientVisible':False}
                db.execute("UPDATE prediction_jobs SET state='SUCCEEDED',result=?,updated_at=?,lease_until=0,error_code=NULL WHERE request_id=?",
                           (json.dumps(record,allow_nan=False),timestamp(),request_id))
                self.store.audit(db,'PREDICTION_COMPLETED',row['prediction_id'],actor.subject,json.dumps({'requestId':request_id,'modelSha256':MODEL_SHA256}))
                return self._view(db.execute('SELECT * FROM prediction_jobs WHERE request_id=?',(request_id,)).fetchone())
        except ClinicalError as error:
            if error.code in {'mapping_conflict','mapping_store_unavailable'}:
                error=ClinicalError(503,'prediction_commit_unavailable')
            with self.store.connection(write=True) as db:
                changed=db.execute("UPDATE prediction_jobs SET state='FAILED',error_code=?,updated_at=?,lease_until=0 WHERE request_id=? AND lease_token=? AND state='PENDING'",
                                   (error.code,timestamp(),request_id,work['lease'])).rowcount
                if changed:
                    self.store.audit(db,'PREDICTION_FAILED',request_id,work['subject'],error.code)
            raise error

    def read(self,bearer,encounter_id):
        def read(db,actor,target):
            self._doctor(db,actor,target)
            results=[]
            for row in db.execute('SELECT * FROM prediction_jobs WHERE encounter_id=? ORDER BY created_at,prediction_id',(target,)):
                review=db.execute('SELECT receipt FROM prediction_reviews WHERE prediction_id=?',(row['prediction_id'],)).fetchone()
                results.append({**self._view(row),'review':json.loads(review['receipt']) if review else None})
            return {'schemaVersion':1,'encounterId':target,'predictions':results,'experimental':True,'patientVisible':False}
        return self.clinical._audited(bearer,encounter_id,'predictions',read)

    def review(self,bearer,encounter_id,prediction_id,command):
        uuid_id(prediction_id)
        fields(command,{'schemaVersion','requestId','expectedReviewVersion','decision','note','attested'})
        request_id=uuid_id(command['requestId'])
        if (type(command['expectedReviewVersion']) is not int or command['expectedReviewVersion']!=0
                or not isinstance(command['decision'],str) or command['decision'] not in {'ACKNOWLEDGED','DISMISSED'} or command['attested'] is not True):
            raise ClinicalError(400,'invalid_prediction_review')
        note=text(command['note'],2000)
        digest=hashlib.sha256(json.dumps([prediction_id,command],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        def review(db,actor,target):
            link=self._doctor(db,actor,target)
            row=db.execute("SELECT * FROM prediction_jobs WHERE prediction_id=? AND encounter_id=? AND state='SUCCEEDED'",(prediction_id,target)).fetchone()
            if not row:
                raise ClinicalError(404,'prediction_not_found')
            previous=db.execute('SELECT * FROM prediction_reviews WHERE prediction_id=? OR request_id=?',(prediction_id,request_id)).fetchone()
            if previous:
                if previous['prediction_id']!=prediction_id or previous['request_id']!=request_id or previous['request_hash']!=digest or previous['actor_subject']!=actor.subject:
                    raise ClinicalError(409,'prediction_review_conflict')
                return json.loads(previous['receipt'])
            receipt={'schemaVersion':1,'requestId':request_id,'predictionId':prediction_id,'reviewVersion':1,
                     'decision':command['decision'],'note':note,'reviewedBy':actor.subject,'mappingId':link['id'],
                     'roleVersion':actor.role_version,'reviewedAt':timestamp(),'attested':True,
                     'experimental':True,'patientVisible':False,'diagnosisApproved':False}
            db.execute('INSERT INTO prediction_reviews VALUES(?,?,?,?,?,?)',(prediction_id,request_id,actor.subject,digest,command['decision'],json.dumps(receipt)))
            self.store.audit(db,'PREDICTION_REVIEWED',prediction_id,actor.subject,json.dumps({'requestId':request_id,'decision':command['decision']}))
            return receipt
        return self.clinical._audited(bearer,encounter_id,'prediction_review',review,audit_action='PREDICTION_ACCESS')

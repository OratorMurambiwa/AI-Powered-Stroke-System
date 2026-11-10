import base64
import hashlib
import json
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4
from clinical_api.errors import ClinicalError
from clinical_api.inference import InferenceAdapter, MODEL_SHA256, MODEL_VERSION, PREPROCESS_VERSION
from clinical_api.tests.test_workflow import WorkflowFixture
from clinical_api.tests.test_assessments import png

class PredictionIntegration(WorkflowFixture,unittest.TestCase):
    database='synthetic_prediction_identity'
    store_version=4

    def setUp(self):
        super().setUp()
        self.service.inference=InferenceAdapter(os.environ['TEST_INFERENCE_URL'],os.environ['INFERENCE_SERVICE_KEY'])
        status,receipt=self.clinical_post('/api/v1/clinical/emergency-assessments',self.emergency('doctor'),'doctor')
        self.assertEqual(status,200)
        self.encounter=receipt['encounterId']
        self.base='/api/v1/clinical/encounters/'+self.encounter
        raw=png()
        status,scan=self.clinical_post(self.base+'/assessment',{'schemaVersion':1,'requestId':str(uuid4()),'expectedVersion':0,
            'action':'SCAN','data':{'mediaType':'image/png','contentBase64':base64.b64encode(raw).decode()}},'doctor')
        self.assertEqual(status,200)
        self.scan=scan['scanId']; self.scan_sha=hashlib.sha256(raw).hexdigest()
        self.technician_assignment=self.assign('technician',self.encounter)

    def intent(self):
        return {'schemaVersion':1,'requestId':str(uuid4()),'scanId':self.scan}

    def infer(self,command=None,user='doctor'):
        return self.clinical_post(self.base+'/predictions',command or self.intent(),user)

    def read(self,user='doctor'):
        return self.request(self.base+'/predictions',user)

    def review(self,prediction_id,command=None,user='doctor'):
        command=command or {'schemaVersion':1,'requestId':str(uuid4()),'expectedReviewVersion':0,
                           'decision':'ACKNOWLEDGED','note':'SYNTHETIC experimental output reviewed; no diagnosis approved.','attested':True}
        return self.clinical_post(self.base+'/predictions/'+prediction_id+'/review',command,user)

    def success(self,command=None):
        status,result=self.infer(command)
        self.assertEqual(status,200); self.assertEqual(result['state'],'SUCCEEDED')
        return result

    def test_actual_private_scan_to_experimental_record_and_doctor_review(self):
        result=self.success(); prediction=result['prediction']
        self.assertEqual(prediction['modelSha256'],MODEL_SHA256); self.assertEqual(prediction['scanSha256'],self.scan_sha)
        self.assertEqual(prediction['modelVersion'],MODEL_VERSION); self.assertEqual(prediction['preprocessingVersion'],PREPROCESS_VERSION)
        self.assertIn(prediction['predictedClass'],{'bleeding','ischemia','normal'})
        self.assertEqual(prediction['rawScore'],max(prediction['scores']))
        self.assertFalse(prediction['patientVisible']); self.assertTrue(prediction['experimental'])
        self.assertIn('completedAt',prediction)
        from clinical_api.tests.harness import ROOT
        contract=json.loads((ROOT/'clinical_api/contracts/experimental-predictions-v1.schema.json').read_text())
        self.assertEqual(set(prediction),set(contract['$defs']['record']['required']))
        status,review=self.review(result['predictionId'])
        self.assertEqual(status,200); self.assertFalse(review['diagnosisApproved'])
        self.assertEqual(self.read()[1]['predictions'][0]['review'],review)
        self.assertEqual(self.request(self.base+'/assessment','doctor')[1]['version'],1)

    def test_authorization_denies_patients_admin_and_assigned_technicians(self):
        for user in ('patientA','patientB','admin','technician','otherDoctor','otherTech'):
            self.assertEqual(self.infer(user=user)[0],403)
            self.assertEqual(self.read(user)[0],403)
            self.assertEqual(self.review(str(uuid4()),user=user)[0],403)
        self.assertEqual(self.request(self.base+'/predictions')[0],401)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM prediction_jobs').fetchone()[0],0)

    def test_wrong_encounter_and_client_model_or_path_are_denied(self):
        other=self.register_person('doctor',3); self.mapping['otherDoctor']=self.link('otherDoctor',other)
        self.assertEqual(self.infer(user='otherDoctor')[0],404)
        self.assertEqual(self.infer({**self.intent(),'scanId':str(uuid4())})[0],404)
        for extra in ({'modelSha256':'0'*64},{'path':'/etc/passwd'},{'url':'https://example.test/image'},{'role':'doctor'},{'schemaVersion':2}):
            self.assertEqual(self.infer({**self.intent(),**extra})[0],400)
        target='/api/v1/clinical/encounters/'+self.encounters[1]+'/predictions'
        self.assertEqual(self.clinical_post(target,self.intent(),'doctor')[0],404)

    def test_concurrent_identical_requests_and_retries_have_one_prediction(self):
        command=self.intent()
        with ThreadPoolExecutor(max_workers=3) as executor:
            # HTTP request deadline is longer than the isolated CPU worker deadline.
            results=list(executor.map(lambda _:self.infer(command),range(3)))
        self.assertTrue(all(s in {200,202} for s,_ in results))
        self.assertEqual(len({r['predictionId'] for _,r in results}),1)
        result=self.success(command)
        self.assertEqual(result['attempts'],1)
        self.assertEqual(self.infer(command),(200,result))
        changed={**command,'scanId':str(uuid4())}
        self.assertIn(self.infer(changed)[0],{404,409})
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM prediction_jobs').fetchone()[0],1)

    def test_actual_worker_failure_retry_recovers_same_record(self):
        command=self.intent(); real=self.service.inference
        self.service.inference=InferenceAdapter('http://127.0.0.1:1/api/v1/predict',os.environ['INFERENCE_SERVICE_KEY'])
        self.assertEqual(self.infer(command)[0],503)
        failed=self.read()[1]['predictions'][0]
        self.assertEqual(failed['state'],'FAILED'); self.assertIsNone(failed['prediction'])
        self.service.inference=real
        result=self.success(command)
        self.assertEqual(result['predictionId'],failed['predictionId']); self.assertEqual(result['attempts'],2)

    def test_retry_limit_and_disabled_configuration_are_fail_closed(self):
        real=self.service.inference; self.service.inference=None
        self.assertEqual(self.infer()[0],503)
        self.service.inference=InferenceAdapter('http://127.0.0.1:1/api/v1/predict',os.environ['INFERENCE_SERVICE_KEY'])
        command=self.intent()
        for _ in range(3):
            self.assertEqual(self.infer(command)[0],503)
        self.assertEqual(self.infer(command)[0],409)
        self.assertEqual(self.read()[1]['predictions'][0]['attempts'],3)
        self.service.inference=real

    def test_invalid_stored_scan_does_not_reach_inference(self):
        with self.store.connection(write=True) as db:
            db.execute('UPDATE assessment_scans SET content=? WHERE id=?',(b'bad-content',self.scan))
        self.assertEqual(self.infer()[0],503)
        self.assertEqual(self.read()[1]['predictions'],[])

    def test_parallel_doctor_reviews_admit_one_and_replays_are_immutable(self):
        result=self.success(); prediction_id=result['predictionId']
        def command(decision):
            return {'schemaVersion':1,'requestId':str(uuid4()),'expectedReviewVersion':0,'decision':decision,'note':'SYNTHETIC reviewed only','attested':True}
        commands=[command('ACKNOWLEDGED'),command('DISMISSED')]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda c:self.review(prediction_id,c),commands))
        self.assertEqual(sorted(s for s,_ in results),[200,409])
        winner=next(i for i,(s,_) in enumerate(results) if s==200)
        self.assertEqual(self.review(prediction_id,commands[winner]),results[winner])
        self.assertFalse(results[winner][1]['diagnosisApproved'])

    def test_approved_human_result_stays_immutable_and_has_no_prediction_fields(self):
        from clinical_api.workflow import NIHSS_MAX
        command={'schemaVersion':1,'requestId':str(uuid4()),'expectedVersion':1,'action':'OBSERVATIONS',
                 'data':{'vitals':{'systolicMmHg':120,'diastolicMmHg':80,'pulseBpm':70,'temperatureC':37,'oxygenPercent':98,'glucoseMgDl':90},
                         'nihss':{k:0 for k in NIHSS_MAX},'observedAt':datetime.now(timezone.utc).isoformat()}}
        self.assertEqual(self.clinical_post(self.base+'/assessment',command,'doctor')[0],200)
        for version,action,data in [(2,'SUBMIT',{}),(3,'APPROVE',{'summary':'SYNTHETIC immutable human observations','attested':True})]:
            self.assertEqual(self.clinical_post(self.base+'/assessment',{'schemaVersion':1,'requestId':str(uuid4()),'expectedVersion':version,'action':action,'data':data},'doctor')[0],200)
        before=self.request(self.base+'/assessment','patientA')[1]
        result=self.success(); self.assertEqual(self.review(result['predictionId'])[0],200)
        after=self.request(self.base+'/assessment','patientA')[1]
        self.assertEqual(before,after)
        self.assertNotIn('predictedClass',json.dumps(after))
        self.assertEqual(self.read('patientA')[0],403)

    def test_revoked_assignment_prevents_replay_and_review(self):
        result=self.success()
        with self.store.connection() as db:
            assignment=db.execute('SELECT id FROM assignments WHERE link_id=? AND encounter_id=? AND revoked_at IS NULL',(self.mapping['doctor']['mappingId'],self.encounter)).fetchone()[0]
        self.manager.revoke({'schemaVersion':1,'id':assignment},'operator','SYNTHETIC revoked assignment',assignment=True)
        self.assertEqual(self.read()[0],404)
        self.assertEqual(self.review(result['predictionId'])[0],404)
        self.assertEqual(self.infer()[0],404)

    def test_revocation_while_real_job_runs_prevents_completion_disclosure(self):
        command=self.intent()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future=executor.submit(self.infer,command)
            for _ in range(100):
                with self.store.connection() as db:
                    row=db.execute('SELECT state FROM prediction_jobs WHERE request_id=?',(command['requestId'],)).fetchone()
                if row and row['state']=='PENDING':
                    break
                time.sleep(0.05)
            else:
                self.fail('real job never reserved')
            self.assertEqual(self.authority_request('auth/logout','doctor',{})[0],204)
            self.assertEqual(future.result()[0],401)
        with self.store.connection() as db:
            row=db.execute('SELECT state,result FROM prediction_jobs WHERE request_id=?',(command['requestId'],)).fetchone()
            self.assertEqual(row['state'],'FAILED'); self.assertIsNone(row['result'])
        user=self.users['doctor']; status,login=self.authority_request('auth/login','doctor',{'email':user['email'],'password':user['password']})
        self.assertEqual(status,200); user['token']=login['token']
        self.assertEqual(self.success(command)['attempts'],2)

    def test_prediction_commit_audit_failure_never_leaves_successful_result(self):
        command=self.intent()
        with self.store.connection(write=True) as db:
            db.execute("CREATE TRIGGER fail_prediction BEFORE INSERT ON audit WHEN NEW.action='PREDICTION_COMPLETED' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        self.assertEqual(self.infer(command)[0],503)
        failed=self.read()[1]['predictions'][0]
        self.assertEqual(failed['state'],'FAILED'); self.assertIsNone(failed['prediction'])
        with self.store.connection(write=True) as db:
            db.execute('DROP TRIGGER fail_prediction')
        self.assertEqual(self.success(command)['attempts'],2)

    def test_worker_rejects_bad_admission_key_and_invalid_image(self):
        from urllib.request import Request,build_opener,ProxyHandler
        from urllib.error import HTTPError
        opener=build_opener(ProxyHandler({}))
        raw=b'<svg/>'
        command={'schemaVersion':1,'modelSha256':MODEL_SHA256,'scanSha256':hashlib.sha256(raw).hexdigest(),
                 'contentBase64':base64.b64encode(raw).decode()}
        for key,expected in [('0'*64,403),(os.environ['INFERENCE_SERVICE_KEY'],400)]:
            request=Request(os.environ['TEST_INFERENCE_URL'],data=json.dumps(command).encode(),
                 headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
            with self.assertRaises(HTTPError) as error:
                opener.open(request,timeout=5)
            self.assertEqual(error.exception.code,expected)

    def test_v4_refuses_existing_v3_store_and_history_read_is_audited(self):
        from clinical_api.store import LinkStore
        path=self.directory/'old-v3.sqlite'
        LinkStore(path,self.source_id,3).initialize()
        before=hashlib.sha256(path.read_bytes()).digest()
        with self.assertRaises(FileExistsError):
            LinkStore(path,self.source_id,4).initialize()
        with self.assertRaises(ClinicalError):
            with LinkStore(path,self.source_id,4).connection():
                pass
        self.assertEqual(hashlib.sha256(path.read_bytes()).digest(),before)
        with self.store.connection(write=True) as db:
            db.execute("CREATE TRIGGER fail_prediction_read BEFORE INSERT ON audit WHEN NEW.action='CLINICAL_READ' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        self.assertEqual(self.read()[0],503)
        with self.store.connection(write=True) as db:
            db.execute('DROP TRIGGER fail_prediction_read')
        self.assertEqual(self.read()[0],200)

    def test_expired_fenced_attempt_cannot_commit_its_output(self):
        command=self.intent()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future=executor.submit(self.infer,command)
            for _ in range(100):
                with self.store.connection() as db:
                    row=db.execute('SELECT state FROM prediction_jobs WHERE request_id=?',(command['requestId'],)).fetchone()
                if row and row['state']=='PENDING':
                    break
                time.sleep(0.05)
            else:
                self.fail('real attempt never reserved')
            # Explicit test-only fence/clock fault; production exposes no force-unlock API.
            with self.store.connection(write=True) as db:
                db.execute('UPDATE prediction_jobs SET lease_token=?,lease_until=0 WHERE request_id=?',(str(uuid4()),command['requestId']))
            self.assertEqual(future.result()[0],409)
        with self.store.connection() as db:
            row=db.execute('SELECT state,result FROM prediction_jobs WHERE request_id=?',(command['requestId'],)).fetchone()
            self.assertEqual(row['state'],'PENDING'); self.assertIsNone(row['result'])
        result=self.success(command)
        self.assertEqual(result['attempts'],2)

    def test_scan_from_another_patient_cannot_be_rebound_to_owned_encounter(self):
        grant=self.grant('doctor',self.patient_b)
        command=self.emergency('doctor',grant=grant)
        command.update(patientId=self.patient_b,patientMappingId=self.mapping['patientB']['mappingId'])
        status,receipt=self.clinical_post('/api/v1/clinical/emergency-assessments',command,'doctor')
        self.assertEqual(status,200)
        target='/api/v1/clinical/encounters/'+receipt['encounterId']+'/predictions'
        self.assertEqual(self.clinical_post(target,self.intent(),'doctor')[0],404)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM prediction_jobs').fetchone()[0],0)

import base64
import binascii
import hashlib
import http.client
import json
import struct
import unittest
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4
from clinical_api.app import ClinicalApplication
from clinical_api.errors import ClinicalError
from clinical_api.store import LinkStore
from clinical_api.workflow import NIHSS_MAX
from clinical_api.tests.test_workflow import WorkflowFixture
from clinical_api.tests.harness import ROOT


def chunk(kind, data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',binascii.crc32(kind+data)&0xffffffff)

def png(width=2, height=2, pixels=None):
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,0,0,0,0))+
            chunk(b'IDAT',zlib.compress(pixels if pixels is not None else b'\0\x80\x90'*height))+chunk(b'IEND',b''))

class AssessmentIntegration(WorkflowFixture, unittest.TestCase):
    database = 'synthetic_assessment_review'
    store_version = 3

    def setUp(self):
        super().setUp()
        status, receipt = self.clinical_post('/api/v1/clinical/emergency-assessments',self.emergency('doctor'),'doctor')
        self.assertEqual(status,200)
        self.encounter = receipt['encounterId']
        self.path = '/api/v1/clinical/encounters/'+self.encounter+'/assessment'
        self.tech_assignment = self.assign('technician',self.encounter)

    def action(self, action='OBSERVATIONS', data=None, version=0):
        if data is None:
            data = {'vitals':{'systolicMmHg':120,'diastolicMmHg':80,'pulseBpm':70,'temperatureC':37,
                             'oxygenPercent':98,'glucoseMgDl':90},'nihss':{k:0 for k in NIHSS_MAX},
                    'observedAt':datetime.now(timezone.utc).isoformat()}
        return {'schemaVersion':1,'requestId':str(uuid4()),'expectedVersion':version,'action':action,'data':data}

    def upload(self, raw=None, version=1):
        return self.action('SCAN',{'mediaType':'image/png','contentBase64':base64.b64encode(png() if raw is None else raw).decode()},version)

    def post(self, command, user='technician'):
        return self.clinical_post(self.path,command,user)

    def read(self, user='doctor'):
        return self.request(self.path,user)

    def ready(self):
        self.assertEqual(self.post(self.action())[0],200)
        status, receipt = self.post(self.upload())
        self.assertEqual(status,200)
        self.assertEqual(self.post(self.action('SUBMIT',{},2))[0],200)
        return receipt['scanId']

    def review(self, decision='APPROVE',version=3,user='doctor'):
        return self.post(self.action(decision,{'summary':'SYNTHETIC clinician-reviewed observations; no diagnosis or treatment inference.','attested':True},version),user)

    def download(self, scan_id, user='doctor', encounter=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.httpd.server_port,timeout=5)
        try:
            headers={'Authorization':self.bearer(user)} if user else {}
            connection.request('GET',f'/api/v1/clinical/encounters/{encounter or self.encounter}/scans/{scan_id}',headers=headers)
            response=connection.getresponse()
            return response.status,response.read(),dict(response.getheaders())
        finally:
            connection.close()

    def test_scheduled_booking_encounter_accepts_assigned_observations(self):
        appointment=self.book()
        status,receipt=self.create(appointment)
        self.assertEqual(status,200)
        self.path='/api/v1/clinical/encounters/'+receipt['encounterId']+'/assessment'
        self.assertEqual(self.post(self.action(),'doctor')[0],200)
        self.assertEqual(self.post(self.action(),'technician')[0],404)
        self.assertEqual(self.read('patientA')[0],404)
        self.assertEqual(self.cancel(appointment)[0],409)

    def test_staff_capture_approval_and_patient_projection(self):
        scan=self.ready()
        self.assertEqual(self.read('patientA')[0],404)
        self.assertEqual(self.download(scan,'patientA')[0],404)
        self.assertEqual(self.review()[0],200)
        status,body,headers=self.read('patientA')
        self.assertEqual(status,200); self.assertEqual(body['state'],'APPROVED')
        self.assertNotIn('notes',body['observations']); self.assertNotIn('history',body)
        self.assertFalse(body['inferencePerformed']); self.assertTrue(body['experimental'])
        self.assertEqual(headers['Cache-Control'],'no-store')
        status,raw,headers=self.download(scan,'patientA')
        self.assertEqual(status,200); self.assertEqual(raw,png())
        self.assertEqual(headers['Content-Type'],'image/png')
        self.assertIn('attachment',headers['Content-Disposition']); self.assertIn('sandbox',headers['Content-Security-Policy'])
        contract=json.loads((ROOT/'clinical_api/contracts/assessment-view-v1.schema.json').read_text())
        self.assertEqual(set(body),set(contract['required']))
        self.assertIn('observedAt',body['observations'])
        history=self.read()[1]['history']
        self.assertEqual([r['version'] for r in history],[1,2,3,4])
        self.assertEqual(history[-1]['role'],'doctor'); self.assertEqual(history[0]['role'],'technician')
        self.assertEqual(history[-1]['mappingId'],self.mapping['doctor']['mappingId'])
        self.assertIn('inputSha256',history[-1]); self.assertEqual(history[-1]['snapshot']['vitals']['pulseBpm'],70)

    def test_cross_patient_admin_and_unassigned_staff_cannot_read_or_upload(self):
        scan=self.ready(); self.review()
        for user,expected in [('patientB',404),('admin',403),('otherDoctor',403),('otherTech',403),('patientA',404)]:
            self.assertEqual(self.post(self.upload(version=4),user)[0],expected)
        for user,expected in [('patientB',404),('admin',403),('otherDoctor',403),('otherTech',403),(None,401)]:
            self.assertEqual(self.read(user)[0],expected)
            self.assertEqual(self.download(scan,user)[0],expected)
        self.assertEqual(self.download(scan,'doctor',self.encounters[1])[0],404)

    def test_technician_cannot_note_or_approve_or_reject(self):
        self.ready()
        for action in ('APPROVE','REJECT'):
            self.assertEqual(self.review(action,user='technician')[0],403)
        self.assertEqual(self.post(self.action('NOTE',{'text':'unauthorized'},3))[0],403)
        self.assertEqual(self.read()[1]['version'],3)

    def test_doctor_notes_remain_private_and_snapshotted(self):
        self.assertEqual(self.post(self.action('NOTE',{'text':'SYNTHETIC internal review note'},0),'doctor')[0],200)
        self.assertEqual(self.read()[1]['observations']['notes'][0]['text'],'SYNTHETIC internal review note')
        self.assertEqual(self.read('patientA')[0],404)
        self.assertEqual(self.read()[1]['history'][0]['snapshot']['notes'][0]['text'],'SYNTHETIC internal review note')

    def test_rejection_allows_correction_then_explicit_resubmission(self):
        self.ready(); self.assertEqual(self.review('REJECT')[0],200)
        self.assertEqual(self.read('patientA')[0],404)
        self.assertEqual(self.post(self.action(version=4))[0],200)
        self.assertEqual(self.read()[1]['state'],'DRAFT')
        self.assertEqual(self.review(version=5)[0],409)
        self.assertEqual(self.post(self.action('SUBMIT',{},5))[0],200)
        self.assertEqual(self.review(version=6)[0],200)
        self.assertEqual(self.read('patientA')[0],200)

    def test_approved_and_submitted_versions_are_frozen(self):
        self.ready()
        self.assertEqual(self.post(self.action(version=3))[0],409)
        self.assertEqual(self.post(self.upload(version=3))[0],409)
        self.assertEqual(self.post(self.action('NOTE',{'text':'late'},3),'doctor')[0],409)
        self.assertEqual(self.review()[0],200)
        self.assertEqual(self.post(self.action(version=4))[0],409)
        self.assertEqual(self.review('REJECT',4)[0],409)

    def test_repeated_mutations_and_uploads_have_single_effect(self):
        command=self.action(); first=self.post(command)
        self.assertEqual(first,self.post(command))
        upload=self.upload(); first=self.post(upload)
        self.assertEqual(first,self.post(upload))
        changed={**upload,'data':{**upload['data'],'contentBase64':base64.b64encode(png(pixels=b'\0\1\2'*2)).decode()}}
        self.assertEqual(self.post(changed)[0],409)
        self.assertEqual(self.read()[1]['version'],2)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM assessment_scans').fetchone()[0],1)
        self.assertEqual(self.post(command,'doctor')[0],409)

    def test_idempotency_replay_does_not_bypass_revoked_assignment(self):
        command=self.action(); self.assertEqual(self.post(command)[0],200)
        self.manager.revoke({'schemaVersion':1,'id':self.tech_assignment['assignmentId']},'operator','SYNTHETIC revocation',assignment=True)
        self.assertEqual(self.post(command)[0],404)
        self.assertEqual(self.read('technician')[0],404)

    def test_parallel_duplicate_uploads_create_one_blob(self):
        self.post(self.action()); command=self.upload()
        with ThreadPoolExecutor(max_workers=4) as executor:
            results=list(executor.map(lambda _:self.post(command),range(4)))
        self.assertTrue(all(s==200 for s,_ in results)); self.assertTrue(all(body==results[0][1] for _,body in results))
        self.assertEqual(self.read()[1]['version'],2)
        self.assertEqual(len(self.read()[1]['observations']['scans']),1)

    def test_parallel_updates_and_reviews_admit_one_expected_version(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda _:self.post(self.action()),range(2)))
        self.assertEqual(sorted(s for s,_ in results),[200,409])
        self.post(self.upload()); self.post(self.action('SUBMIT',{},2))
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(self.review,['APPROVE','REJECT']))
        self.assertEqual(sorted(s for s,_ in results),[200,409])
        self.assertEqual(self.read()[1]['version'],4)

    def test_bad_vitals_and_nihss_are_rejected_without_partial_change(self):
        for field,value in [('pulseBpm',True),('temperatureC',99),('oxygenPercent',-1),('systolicMmHg','120')]:
            command=self.action(); command['data']['vitals'][field]=value
            self.assertEqual(self.post(command)[0],400)
        for field,value in [('leftArm',5),('neglect',True),('gaze',-1)]:
            command=self.action(); command['data']['nihss'][field]=value
            self.assertEqual(self.post(command)[0],400)
        command=self.action(); del command['data']['nihss']['gaze']; self.assertEqual(self.post(command)[0],400)
        command=self.action(); command['data']['observedAt']='2099-01-01T00:00:00+00:00'; self.assertEqual(self.post(command)[0],400)
        self.assertEqual(self.read()[1]['version'],0)

    def test_incomplete_and_unattested_review_transitions_fail(self):
        self.assertEqual(self.post(self.action('SUBMIT',{}))[0],409)
        self.assertEqual(self.review(version=0)[0],409)
        self.ready()
        for data in ({'summary':'no attestation'},{'summary':'synthetic','attested':False},{'summary':'','attested':True}):
            self.assertEqual(self.post(self.action('APPROVE',data,3),'doctor')[0],400)
        self.assertEqual(self.read('patientA')[0],404)

    def test_malicious_scan_types_contents_and_paths_rejected(self):
        self.post(self.action())
        for raw in [b'<svg onload="alert(1)"/>',b'%PDF-1.4 fake',b'MZexecutable',b'DICM',png()+b'<script>',png()[:-1],png(0),png(2048),png(pixels=b'\5\0\0'*2)]:
            self.assertEqual(self.post(self.upload(raw))[0],400)
        raw=bytearray(png()); raw[29]^=1; self.assertEqual(self.post(self.upload(bytes(raw)))[0],400)
        for extra in ({'filename':'../../credentials'},{'path':'/tmp/stolen'},{'mediaType':'text/html'}):
            command=self.upload(); command['data'].update(extra); self.assertEqual(self.post(command)[0],400)
        command=self.upload(); command['data']['contentBase64']='%%%%'; self.assertEqual(self.post(command)[0],400)
        self.assertEqual(self.read()[1]['version'],1)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM assessment_scans').fetchone()[0],0)

    def test_decompression_bombs_metadata_and_oversize_rejected(self):
        self.post(self.action())
        self.assertEqual(self.post(self.upload(png(pixels=b'\0'*(4*1024*1024))))[0],400)
        raw=png(); raw=raw[:33]+chunk(b'tEXt',b'executable metadata')+raw[33:]
        self.assertEqual(self.post(self.upload(raw))[0],400)
        self.assertEqual(self.post(self.upload(b'\0'*1048577))[0],413)
        self.assertEqual(self.read()[1]['version'],1)

    def test_blob_and_state_rollback_on_audit_failure_then_recover(self):
        self.post(self.action()); command=self.upload()
        with self.store.connection(write=True) as db:
            db.execute("CREATE TRIGGER fail_mutation BEFORE INSERT ON audit WHEN NEW.action='ASSESSMENT_SCAN' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        self.assertEqual(self.post(command)[0],503)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM assessment_scans').fetchone()[0],0)
        self.assertEqual(self.read()[1]['version'],1)
        with self.store.connection(write=True) as db:
            db.execute('DROP TRIGGER fail_mutation')
        self.assertEqual(self.post(command)[0],200)

    def test_scan_read_requires_committed_audit_and_detects_corruption(self):
        scan=self.ready()
        with self.store.connection(write=True) as db:
            db.execute("CREATE TRIGGER fail_download BEFORE INSERT ON audit WHEN NEW.action='CLINICAL_READ' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        status,raw,_=self.download(scan)
        self.assertEqual(status,503); self.assertNotEqual(raw,png())
        with self.store.connection(write=True) as db:
            db.execute('DROP TRIGGER fail_download')
            db.execute('UPDATE assessment_scans SET content=? WHERE id=?',(b'corrupt',scan))
        self.assertEqual(self.download(scan)[0],503)

    def test_authority_outage_and_storage_outage_fail_closed_then_recover(self):
        # Use an actually refused loopback port, not a mocked successful introspection.
        from clinical_api.identity import IdentityAdapter
        self.service.identity=IdentityAdapter('http://127.0.0.1:1/api/v1/identity/clinical-introspect')
        self.assertEqual(self.post(self.action())[0],503)
        self.service.identity=self.adapter
        self.links.rename(self.links.with_suffix('.offline'))
        self.assertEqual(self.post(self.action())[0],503)
        self.links.with_suffix('.offline').rename(self.links)
        self.assertEqual(self.post(self.action())[0],200)

    def test_patient_legacy_path_does_not_leak_unapproved_source_details(self):
        status,body,_=self.request('/api/v1/clinical/encounters/'+self.encounters[0],'patientA')
        self.assertEqual(status,200); self.assertEqual(body['encounter'],{'status':'LEGACY_RESULT_UNAVAILABLE'})
        self.assertNotIn('vitals',json.dumps(body))

    def test_fresh_v3_store_refuses_existing_v2_without_modification(self):
        path=self.directory/'fresh-v2.sqlite'
        LinkStore(path,self.source_id,2).initialize(); before=hashlib.sha256(path.read_bytes()).digest()
        with self.assertRaises(FileExistsError):
            LinkStore(path,self.source_id,3).initialize()
        with self.assertRaises(ClinicalError):
            with LinkStore(path,self.source_id,3).connection():
                pass
        self.assertEqual(hashlib.sha256(path.read_bytes()).digest(),before)

    def test_audit_history_excludes_payloads_and_secrets(self):
        self.post(self.action()); self.post(self.upload())
        self.post(self.upload(),'patientB')
        with self.store.connection() as db:
            rows=[dict(r) for r in db.execute("SELECT * FROM audit WHERE action IN ('ASSESSMENT_ACCESS','CLINICAL_READ','ASSESSMENT_SCAN','ASSESSMENT_OBSERVATIONS')")]
        raw=json.dumps(rows)
        self.assertIn('denied',raw); self.assertIn('allowed',raw)
        for secret in [base64.b64encode(png()).decode(),'systolicMmHg',self.users['doctor']['token'],self.users['technician']['password']]:
            self.assertNotIn(secret,raw)

    def test_approval_retry_is_immutable_and_changed_decision_conflicts(self):
        self.ready()
        command=self.action('APPROVE',{'summary':'SYNTHETIC approved human summary','attested':True},3)
        first=self.post(command,'doctor')
        self.assertEqual(first[0],200)
        self.assertEqual(first,self.post(command,'doctor'))
        altered={**command,'action':'REJECT'}
        self.assertEqual(self.post(altered,'doctor')[0],409)
        schema=json.loads((ROOT/'clinical_api/contracts/assessment-action-receipt-v1.schema.json').read_text())
        self.assertEqual(set(first[1]),set(schema['required']))
        self.assertEqual(len(self.read()[1]['history']),4)

    def test_assignment_and_link_revocation_deny_download_and_pending_approval(self):
        scan=self.ready()
        self.manager.revoke({'schemaVersion':1,'id':self.tech_assignment['assignmentId']},'operator','SYNTHETIC revoke',assignment=True)
        self.assertEqual(self.download(scan,'technician')[0],404)
        self.manager.revoke({'schemaVersion':1,'id':self.mapping['doctor']['mappingId']},'operator','SYNTHETIC revoke link')
        self.assertEqual(self.review()[0],403)
        self.assertEqual(self.download(scan)[0],403)
        self.assertEqual(self.read('patientA')[0],404)

    def test_expired_session_cannot_capture_or_read(self):
        self.command('expire',user='technician')
        self.assertEqual(self.post(self.action())[0],401)
        self.assertEqual(self.read('technician')[0],401)
        # Restore a fresh real authority session for subsequent independent cases.
        user=self.users['technician']
        status,body=self.authority_request('auth/login','technician',{'email':user['email'],'password':user['password']})
        self.assertEqual(status,200); user['token']=body['token']
        self.assertEqual(self.post(self.action())[0],200)

    def test_unknown_contract_keys_and_version_cannot_assign_privileges(self):
        for extra in ({'role':'doctor'},{'schemaVersion':2},{'expectedVersion':True},{'patientId':self.patient_b}):
            command=self.action(); command.update(extra)
            self.assertEqual(self.post(command)[0],400)
        self.assertEqual(self.read()[1]['version'],0)

    def test_z_revoked_staff_session_denies_reads_writes_and_downloads(self):
        scan=self.ready(); command=self.action('NOTE',{'text':'SYNTHETIC'},3)
        self.assertEqual(self.authority_request('auth/logout','doctor',{})[0],204)
        self.assertEqual(self.post(command,'doctor')[0],401)
        self.assertEqual(self.read()[0],401); self.assertEqual(self.download(scan)[0],401)
        user=self.users['doctor']
        status,body=self.authority_request('auth/login','doctor',{'email':user['email'],'password':user['password']})
        self.assertEqual(status,200); user['token']=body['token']
        self.assertEqual(self.read()[0],200)

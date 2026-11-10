import http.client
import json
import sqlite3
import time
from datetime import date, timedelta
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from clinical_api.errors import ClinicalError
from clinical_api.tests.harness import ClinicalFixture, ROOT

class ResponseFault:
    """Test-only HTTP response faults around the actual application/SQLite commit."""
    def __init__(self, application):
        self.application = application
        self.mode = None
        self.requests = 0
    def __call__(self, environ, start_response):
        if environ.get('PATH_INFO') != '/api/v1/clinical/assessment-requests':
            return self.application(environ, start_response)
        self.requests += 1
        if self.mode == 'before':
            raw = b'{"schemaVersion":1,"error":"synthetic_unavailable"}'
            start_response('503 Service Unavailable', [('Content-Type','application/json'),('Content-Length',str(len(raw)))])
            return [raw]
        captured = []
        def capture(status, headers):
            captured.extend([status,headers])
        raw = b''.join(self.application(environ, capture))
        if self.mode == 'after':
            raw = b'{"schemaVersion":1,"error":"synthetic_lost_ack"}'
            captured = ['503 Service Unavailable',[('Content-Type','application/json'),('Content-Length',str(len(raw)))]]
        elif self.mode == 'malformed':
            raw = b'{"schemaVersion":1,"state":"CREATED","requestId":"not-the-request"}'
            captured = ['200 OK',[('Content-Type','application/json'),('Content-Length',str(len(raw)))]]
        start_response(*captured)
        return [raw]

class WorkflowFixture(ClinicalFixture):
    database = 'synthetic_workflow_identity'
    store_version = 2
    booking_day = 0

    def setUp(self):
        super().setUp()
        self.command('resetLimits')
        self.fault = ResponseFault(self.httpd.get_app())
        self.httpd.set_app(self.fault)
        self.clinical_url = f'http://127.0.0.1:{self.httpd.server_port}/api/v1/clinical/assessment-requests'
        self.command('clinicalUrl', url=self.clinical_url)
        self.counter = 0
        type(self).booking_day += 1
        self.booking_date = (date(2099,9,1)+timedelta(days=type(self).booking_day)).isoformat()

    def node(self, method, path, user, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=8)
        try:
            headers = {'Content-Type':'application/json'}
            if user:
                headers['Authorization'] = self.bearer(user)
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
        finally:
            connection.close()

    def book(self, patient='patientA', doctor='doctor'):
        self.counter += 1
        start = f'{8+self.counter:02d}:00'
        end = f'{9+self.counter:02d}:00'
        status, slot = self.node('POST','/api/availability',doctor,{'date':self.booking_date,'startTime':start,'endTime':end})
        self.assertEqual(status,201)
        status, appointment = self.node('POST','/api/v1/appointments',patient,{'schemaVersion':1,'availabilityId':slot['availability']['_id']})
        self.assertEqual(status,201)
        self.assertEqual(appointment['status'],'confirmed')
        contract=json.loads((ROOT/'booking-backend/contracts/appointment-v1.schema.json').read_text())
        self.assertEqual(set(appointment),set(contract['required']))
        return appointment

    def intent(self):
        return {'schemaVersion':1,'requestId':str(uuid4()),'sourceId':self.source_id,'patientId':self.people['patient'],
                'patientMappingId':self.mapping['patientA']['mappingId'],'clinicianMappingId':self.mapping['doctor']['mappingId']}

    def create(self, appointment, intent=None, user='doctor'):
        return self.node('POST',f"/api/v1/appointments/{appointment['appointmentId']}/assessment-requests",user,intent or self.intent())

    def cancel(self, appointment, user='patientA'):
        return self.node('PATCH',f"/api/v1/appointments/{appointment['appointmentId']}/cancel",user,{'schemaVersion':1})

    def count(self, table):
        assert table in {'assessment_records','assessment_receipts','assignments','intake_grants'}
        with self.store.connection() as db:
            return db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]

    def grant(self, user='technician', patient_id=None):
        return self.manager.grant_intake({'schemaVersion':1,'mappingId':self.mapping[user]['mappingId'],
             'patientId':patient_id or self.people['patient'],'expiresAt':int(time.time())+3600},
             self.bearer(user),'synthetic-operator','SYNTHETIC patient-scoped emergency intake')

    def emergency(self, user='technician', grant=None):
        grant = grant or self.grant(user)
        return {'schemaVersion':1,'requestId':str(uuid4()),'sourceId':self.source_id,'patientId':self.people['patient'],
                'patientMappingId':self.mapping['patientA']['mappingId'],'actorMappingId':self.mapping[user]['mappingId'],
                'intakeGrantId':grant['intakeGrantId'],'reasonCode':'SUSPECTED_STROKE'}

    def clinical_post(self, path, body, user='technician'):
        connection = http.client.HTTPConnection('127.0.0.1',self.httpd.server_port,timeout=30)
        try:
            connection.request('POST',path,json.dumps(body),{'Content-Type':'application/json','Authorization':self.bearer(user)})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

class WorkflowIntegration(WorkflowFixture, unittest.TestCase):
    def test_confirmed_booking_to_owned_assigned_encounter(self):
        appointment = self.book()
        intent = self.intent()
        status, workflow = self.create(appointment,intent)
        self.assertEqual(status,200)
        self.assertEqual(workflow['state'],'CREATED')
        self.assertEqual(self.count('assessment_records'),1)
        for actor in ('patientA','doctor'):
            status, record, _ = self.request('/api/v1/clinical/encounters/'+workflow['encounterId'],actor)
            self.assertEqual(status,200)
            self.assertEqual(record['encounter']['appointmentId'],appointment['appointmentId'])
            self.assertEqual(record['encounter']['status'],'ASSESSMENT_PENDING')
            self.assertTrue(record['experimental'] and record['clinicianReviewRequired'])
        for actor, expected in [('patientB',404),('technician',404),('otherDoctor',403),('admin',403)]:
            self.assertEqual(self.request('/api/v1/clinical/encounters/'+workflow['encounterId'],actor)[0],expected)
        self.assertEqual(self.node('GET','/api/v1/appointments/'+appointment['appointmentId'],'patientB')[0],404)
        self.assertEqual(self.node('GET','/api/v1/appointments/'+appointment['appointmentId'],'admin')[0],403)
        self.assertEqual(self.cancel(appointment)[0],409)
        legacy=self.node('GET','/api/appointments','patientA')[1]['appointments']
        native=next(row['_id'] for row in legacy if row.get('appointmentUuid')==appointment['appointmentId'])
        self.assertEqual(self.node('PATCH',f'/api/appointments/{native}/cancel','patientA',{})[0],409)
        state_contract=json.loads((ROOT/'booking-backend/contracts/assessment-state-v1.schema.json').read_text())
        self.assertEqual(set(workflow),set(state_contract['required']))
        status, current = self.node('GET','/api/v1/appointments/'+appointment['appointmentId'],'patientA')
        self.assertEqual(current['encounterId'],workflow['encounterId'])
        self.assertEqual(current['status'],'confirmed')

    def test_duplicate_and_conflicting_intents_are_idempotent(self):
        appointment = self.book(); intent = self.intent()
        first = self.create(appointment,intent)
        second = self.create(appointment,intent)
        self.assertEqual(first,second)
        self.assertEqual(self.count('assessment_records'),1)
        self.assertEqual(self.count('assessment_receipts'),1)
        altered = {**intent,'patientId':self.patient_b}
        self.assertEqual(self.create(appointment,altered)[0],409)
        self.assertEqual(self.create(appointment,self.intent())[0],409)
        self.assertEqual(self.count('assessment_records'),1)

    def test_concurrent_duplicate_requests_persist_one_record_and_assignment(self):
        appointment = self.book(); intent = self.intent()
        with ThreadPoolExecutor(max_workers=6) as executor:
            outcomes = list(executor.map(lambda _: self.create(appointment,intent),range(6)))
        self.assertTrue(all(status in {200,202} for status,_ in outcomes))
        self.assertTrue(any(body['state']=='CREATED' for _,body in outcomes))
        self.assertEqual(len({body['encounterId'] for _,body in outcomes}),1)
        self.assertEqual(self.count('assessment_records'),1)
        self.assertEqual(self.count('assignments'),1)

    def test_concurrent_distinct_intents_for_one_appointment_admit_one(self):
        appointment = self.book()
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: self.create(appointment,self.intent()),range(2)))
        self.assertEqual(sorted(status for status,_ in outcomes),[200,409])
        self.assertEqual(self.count('assessment_records'),1)

    def test_global_request_id_collision_between_owners_cannot_rebind(self):
        other_person=self.register_person('doctor',3)
        other_link=self.link('otherDoctor',other_person)
        first=self.book()
        second=self.book('patientB','otherDoctor')
        first_intent=self.intent()
        second_intent={**first_intent,'patientId':self.patient_b,'patientMappingId':self.mapping['patientB']['mappingId'],'clinicianMappingId':other_link['mappingId']}
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_call=executor.submit(self.create,first,first_intent,'doctor')
            second_call=executor.submit(self.create,second,second_intent,'otherDoctor')
            results=[first_call.result(),second_call.result()]
        self.assertEqual(sorted(status for status,_ in results),[200,409])
        conflict=next(body for status,body in results if status==409)
        self.assertEqual(conflict['schemaVersion'],1)
        self.assertEqual(self.count('assessment_records'),1)
        self.assertEqual(self.count('assessment_receipts'),1)

    def test_wrong_patient_is_durably_rejected_and_does_not_lock_booking(self):
        appointment = self.book(); intent = self.intent()
        invalid = {**intent,'patientId':self.patient_b,'patientMappingId':self.mapping['patientB']['mappingId']}
        status, receipt = self.create(appointment,invalid)
        self.assertEqual(status,422); self.assertEqual(receipt['state'],'REJECTED')
        self.assertEqual(self.count('assessment_records'),0)
        self.assertEqual(self.create(appointment,invalid),(status,receipt))
        self.assertEqual(self.create(appointment,self.intent())[0],200)
        self.assertEqual(self.count('assessment_records'),1)

    def test_wrong_clinician_mapping_rejects_without_clinical_write(self):
        appointment = self.book(); intent = self.intent()
        intent['clinicianMappingId'] = self.mapping['technician']['mappingId']
        self.assertEqual(self.create(appointment,intent)[0],422)
        self.assertEqual(self.count('assessment_records'),0)
        self.assertEqual(self.cancel(appointment)[0],200)

    def test_only_assigned_doctor_can_start_scheduled_assessment(self):
        appointment = self.book()
        for user, expected in [('patientA',403),('patientB',403),('technician',403),('admin',403),('otherDoctor',404)]:
            self.assertEqual(self.create(appointment,self.intent(),user)[0],expected)
        self.assertEqual(self.count('assessment_records'),0)
        self.assertEqual(self.cancel(appointment,'patientB')[0],404)

    def test_cancelled_and_completed_appointments_cannot_start_encounters(self):
        cancelled = self.book()
        self.assertEqual(self.cancel(cancelled)[0],200)
        self.assertEqual(self.create(cancelled)[0],409)
        completed = self.book()
        self.command('appointmentStatus',appointmentId=completed['appointmentId'],status='completed')
        self.assertEqual(self.create(completed)[0],409)
        self.assertEqual(self.count('assessment_records'),0)

    def test_concurrent_cancel_and_create_never_cancel_a_started_encounter(self):
        appointment = self.book(); intent = self.intent()
        with ThreadPoolExecutor(max_workers=2) as executor:
            creating = executor.submit(self.create,appointment,intent)
            cancelling = executor.submit(self.cancel,appointment)
            created, cancelled = creating.result(),cancelling.result()
        self.assertIn((created[0],cancelled[0]),{(200,409),(409,200)})
        current = self.node('GET','/api/v1/appointments/'+appointment['appointmentId'],'patientA')[1]
        self.assertEqual(self.count('assessment_records'),1 if created[0]==200 else 0)
        self.assertEqual(current['status'],'confirmed' if created[0]==200 else 'cancelled')

    def test_unavailable_clinical_service_keeps_durable_pending_then_recovers(self):
        appointment = self.book(); intent = self.intent()
        self.command('clinicalUrl',url='http://127.0.0.1:1/api/v1/clinical/assessment-requests')
        status, pending = self.create(appointment,intent)
        self.assertEqual(status,202); self.assertEqual(pending['state'],'PENDING')
        self.assertEqual(self.cancel(appointment)[0],409)
        self.assertEqual(self.count('assessment_records'),0)
        self.command('clinicalUrl',url=self.clinical_url)
        self.command('expireLease',requestId=intent['requestId'])
        status, created = self.create(appointment,intent)
        self.assertEqual(status,200)
        self.assertEqual(created['encounterId'],pending['encounterId'])
        self.assertEqual(self.count('assessment_records'),1)

    def test_clinical_commit_with_lost_ack_replays_without_duplicate(self):
        appointment = self.book(); intent = self.intent(); self.fault.mode='after'
        status, pending = self.create(appointment,intent)
        self.assertEqual(status,202); self.assertEqual(self.count('assessment_records'),1)
        self.assertEqual(self.cancel(appointment)[0],409)
        self.fault.mode=None
        self.command('expireLease',requestId=intent['requestId'])
        status, created = self.create(appointment,intent)
        self.assertEqual(status,200); self.assertEqual(created['encounterId'],pending['encounterId'])
        self.assertEqual(self.count('assessment_records'),1); self.assertEqual(self.count('assignments'),1)

    def test_malformed_ack_never_releases_reservation(self):
        appointment = self.book(); intent = self.intent(); self.fault.mode='malformed'
        self.assertEqual(self.create(appointment,intent)[0],202)
        self.assertEqual(self.cancel(appointment)[0],409)
        self.fault.mode=None; self.command('expireLease',requestId=intent['requestId'])
        self.assertEqual(self.create(appointment,intent)[0],200)
        self.assertEqual(self.count('assessment_records'),1)

    def test_mongo_ack_failure_after_clinical_commit_recovers(self):
        for expected,kind in enumerate(('request','appointment'),start=1):
            appointment = self.book(); intent=self.intent(); self.command('failFinalize',kind=kind)
            self.assertEqual(self.create(appointment,intent)[0],503)
            self.assertEqual(self.count('assessment_records'),expected)
            state = self.command('inspectWorkflow',requestId=intent['requestId'])
            self.assertEqual(state['state'],'PENDING'); self.assertTrue(state['blocking'])
            self.assertEqual(state['reservations'],1)
            self.command('expireLease',requestId=intent['requestId'])
            self.assertEqual(self.create(appointment,intent)[0],200)
            self.assertEqual(self.count('assessment_records'),expected)

    def test_creation_audit_failure_rolls_back_clinical_data_then_retry_succeeds(self):
        appointment=self.book(); intent=self.intent()
        with self.store.connection(write=True) as db:
            db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT,'synthetic audit failure'); END")
        self.assertEqual(self.create(appointment,intent)[0],202)
        self.assertEqual(self.count('assessment_records'),0); self.assertEqual(self.count('assessment_receipts'),0)
        with self.store.connection(write=True) as db:
            db.execute('DROP TRIGGER fail_audit')
        self.command('expireLease',requestId=intent['requestId'])
        self.assertEqual(self.create(appointment,intent)[0],200)
        self.assertEqual(self.count('assessment_records'),1)

    def test_read_audits_record_allowed_denied_and_invalid_sessions_without_payloads(self):
        self.request('/api/v1/clinical/patients/'+self.people['patient'],'patientA')
        self.request('/api/v1/clinical/patients/'+self.people['patient'],'patientB')
        self.request('/api/v1/clinical/patients/'+self.people['patient'],'admin')
        self.request('/api/v1/clinical/patients/'+self.people['patient'])
        with self.store.connection() as db:
            audits=[dict(row) for row in db.execute("SELECT * FROM audit WHERE action='CLINICAL_READ' ORDER BY at,id")]
        reasons=[json.loads(row['reason']) for row in audits]
        self.assertEqual([r['status'] for r in reasons],[200,404,403,401])
        self.assertEqual([r['outcome'] for r in reasons],['allowed','denied','denied','denied'])
        raw=json.dumps(audits)
        self.assertNotIn('Synthetic Patient',raw)
        for user in self.users.values():
            self.assertNotIn(user['token'],raw); self.assertNotIn(user['email'],raw); self.assertNotIn(user['password'],raw)

    def test_read_audit_failure_blocks_disclosure_and_recovers(self):
        with self.store.connection(write=True) as db:
            db.execute("CREATE TRIGGER fail_read BEFORE INSERT ON audit WHEN NEW.action='CLINICAL_READ' BEGIN SELECT RAISE(ABORT,'synthetic read audit failure'); END")
        status,body,_=self.request('/api/v1/clinical/patients/'+self.people['patient'],'patientA')
        self.assertEqual(status,503); self.assertNotIn('demographics',body)
        with self.store.connection(write=True) as db:
            db.execute('DROP TRIGGER fail_read')
        self.assertEqual(self.request('/api/v1/clinical/patients/'+self.people['patient'],'patientA')[0],200)

    def test_emergency_encounters_need_no_appointment_for_granted_staff(self):
        for user in ('doctor','technician'):
            command=self.emergency(user)
            status,receipt=self.clinical_post('/api/v1/clinical/emergency-assessments',command,user)
            self.assertEqual(status,200); self.assertIsNone(receipt['appointmentId'])
            self.assertEqual(receipt['state'],'CREATED')
            self.assertEqual(self.request('/api/v1/clinical/encounters/'+receipt['encounterId'],user)[0],200)
            self.assertEqual(self.request('/api/v1/clinical/encounters/'+receipt['encounterId'],'patientA')[0],200)
            self.assertEqual(self.request('/api/v1/clinical/encounters/'+receipt['encounterId'],'patientB')[0],404)
        self.assertEqual(self.count('assessment_records'),2)

    def test_emergency_duplicate_concurrent_requests_are_idempotent(self):
        command=self.emergency()
        with ThreadPoolExecutor(max_workers=4) as executor:
            results=list(executor.map(lambda _:self.clinical_post('/api/v1/clinical/emergency-assessments',command),range(4)))
        self.assertTrue(all(status==200 for status,_ in results))
        self.assertEqual(len({body['encounterId'] for _,body in results}),1)
        self.assertEqual(self.count('assessment_records'),1); self.assertEqual(self.count('assignments'),1)
        altered={**command,'reasonCode':'URGENT_REASSESSMENT'}
        self.assertEqual(self.clinical_post('/api/v1/clinical/emergency-assessments',altered)[0],409)

    def test_emergency_intake_grants_are_patient_scoped_expiring_and_revocable(self):
        grant=self.grant(); command=self.emergency(grant=grant)
        invalid={**command,'intakeGrantId':str(uuid4())}
        self.assertEqual(self.clinical_post('/api/v1/clinical/emergency-assessments',invalid)[0],403)
        other={**command,'patientId':self.patient_b,'patientMappingId':self.mapping['patientB']['mappingId']}
        self.assertEqual(self.clinical_post('/api/v1/clinical/emergency-assessments',other)[0],403)
        for user in ('patientA','admin','otherTech'):
            self.assertIn(self.clinical_post('/api/v1/clinical/emergency-assessments',command,user)[0],{403,409})
        self.manager.revoke_intake({'schemaVersion':1,'id':grant['intakeGrantId']},'operator','SYNTHETIC revoke intake')
        self.assertEqual(self.clinical_post('/api/v1/clinical/emergency-assessments',command)[0],403)
        new=self.grant(); command=self.emergency(grant=new)
        with self.store.connection(write=True) as db:
            db.execute('UPDATE intake_grants SET expires_at=0 WHERE id=?',(new['intakeGrantId'],))
        self.assertEqual(self.clinical_post('/api/v1/clinical/emergency-assessments',command)[0],403)
        self.assertEqual(self.count('assessment_records'),0)

    def test_unconfigured_service_and_bad_contracts_do_not_create_reservations(self):
        appointment=self.book(); intent=self.intent()
        self.command('clinicalUrl',url='https://example.com/api/v1/clinical/assessment-requests')
        self.assertEqual(self.create(appointment,intent)[0],503)
        state=self.command('inspectWorkflow',requestId=intent['requestId'])
        self.assertIsNone(state['state']); self.assertEqual(state['reservations'],0)
        self.command('clinicalUrl',url=self.clinical_url)
        self.assertEqual(self.create(appointment,{**intent,'schemaVersion':2})[0],400)
        self.assertEqual(self.create(appointment,{**intent,'patientSubject':self.users['patientB']['id']})[0],400)
        self.assertEqual(self.node('POST','/api/v1/appointments/not-uuid/assessment-requests','doctor',intent)[0],400)
        self.assertEqual(self.count('assessment_records'),0)

    def test_direct_clinical_command_cannot_change_reserved_patient_context(self):
        appointment=self.book(); intent=self.intent(); self.fault.mode='before'
        status,pending=self.create(appointment,intent)
        self.assertEqual(status,202)
        self.fault.mode=None
        payload={**intent,'mode':'SCHEDULED','appointmentId':appointment['appointmentId'],'encounterId':pending['encounterId']}
        tampered={**payload,'patientId':self.patient_b,'patientMappingId':self.mapping['patientB']['mappingId']}
        self.assertEqual(self.clinical_post('/api/v1/clinical/assessment-requests',tampered,'doctor')[0],503)
        self.assertEqual(self.count('assessment_records'),0)
        status,receipt=self.clinical_post('/api/v1/clinical/assessment-requests',payload,'doctor')
        self.assertEqual(status,200)
        contract=json.loads((ROOT/'clinical_api/contracts/assessment-receipt-v1.schema.json').read_text())
        self.assertEqual(set(receipt),set(contract['required']))
        self.command('expireLease',requestId=intent['requestId'])
        self.assertEqual(self.create(appointment,intent)[0],200)
        self.assertEqual(self.count('assessment_records'),1)

    def test_z_revoked_sessions_and_pending_retry_after_fresh_login(self):
        appointment=self.book(); intent=self.intent()
        self.fault.mode='before'; self.assertEqual(self.create(appointment,intent)[0],202)
        self.assertEqual(self.authority_request('auth/logout','doctor',{})[0],204)
        self.assertEqual(self.create(appointment,intent)[0],401)
        user=self.users['doctor']
        status,result=self.authority_request('auth/login','doctor',{'email':user['email'],'password':user['password']})
        self.assertEqual(status,200); user['token']=result['token']
        self.fault.mode=None; self.command('expireLease',requestId=intent['requestId'])
        self.assertEqual(self.create(appointment,intent)[0],200)
        admin=self.users['admin']
        self.assertEqual(self.authority_request(f"staff/{user['id']}/revoke",'admin',{'currentPassword':admin['password'],'reason':'SYNTHETIC offboarding'})[0],200)
        self.assertEqual(self.create(appointment,intent)[0],401)
        self.assertEqual(self.request('/api/v1/clinical/encounters/'+self.create(appointment,intent)[1].get('encounterId',str(uuid4())),'doctor')[0],401)

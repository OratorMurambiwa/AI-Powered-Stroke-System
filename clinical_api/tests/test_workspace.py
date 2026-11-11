import unittest
from uuid import uuid4
from clinical_api.tests.test_workflow import WorkflowFixture
from clinical_api.workflow import NIHSS_MAX
from datetime import datetime,timezone

class WorkspaceIntegration(WorkflowFixture,unittest.TestCase):
    store_version=4
    database='synthetic_workspace_identity'
    def setUp(self):
        super().setUp()
        status,receipt=self.clinical_post('/api/v1/clinical/emergency-assessments',self.emergency('doctor'),'doctor')
        self.assertEqual(status,200);self.encounter=receipt['encounterId']
    def workspace(self,user):return self.request('/api/v1/clinical/workspace',user)
    def test_assigned_discovery_and_patient_approval_filter(self):
        self.assertEqual(len(self.workspace('doctor')[1]['encounters']),1)
        self.assertEqual(self.workspace('technician')[1]['encounters'],[])
        self.assertEqual(self.workspace('patientA')[1]['encounters'],[])
        assignment=self.assign('technician',self.encounter)
        self.assertEqual(self.workspace('technician')[1]['encounters'][0]['encounterId'],self.encounter)
        self.manager.revoke({'schemaVersion':1,'id':assignment['assignmentId']},'operator','SYNTHETIC removal',assignment=True)
        self.assertEqual(self.workspace('technician')[1]['encounters'],[])
        self.assertEqual(self.workspace('patientB')[1]['encounters'],[])
    def test_admin_unlinked_and_invalid_sessions_cannot_discover(self):
        for user,status in [('admin',403),('otherDoctor',403),(None,401)]:self.assertEqual(self.workspace(user)[0],status)
    def test_workspace_audit_failure_prevents_disclosure(self):
        with self.store.connection(write=True) as db:db.execute("CREATE TRIGGER fail_workspace BEFORE INSERT ON audit WHEN NEW.action='CLINICAL_READ' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        status,body,_=self.workspace('doctor');self.assertEqual(status,503);self.assertNotIn('encounters',body)
    def test_confirmed_owned_context_uses_exact_mapping(self):
        appointment=self.book();path='/api/v1/clinical/appointment-context/'+appointment['appointmentId']
        status,result,_=self.request(path,'doctor');self.assertEqual(status,200)
        self.assertEqual(result['patientMappingId'],self.mapping['patientA']['mappingId'])
        self.assertEqual(result['clinicianMappingId'],self.mapping['doctor']['mappingId'])
        for actor in ['patientA','technician','admin']:self.assertEqual(self.request(path,actor)[0],403)
        self.assertEqual(self.cancel(appointment)[0],200)
        self.assertEqual(self.request(path,'doctor')[0],409)
    def test_context_unlinked_patient_and_booking_outage_fail_closed(self):
        appointment=self.book();path='/api/v1/clinical/appointment-context/'+appointment['appointmentId']
        self.manager.revoke({'schemaVersion':1,'id':self.mapping['patientA']['mappingId']},'operator','SYNTHETIC unlink')
        self.assertEqual(self.request(path,'doctor')[0],409)
        self.command('pause')
        try:self.assertEqual(self.request(path,'doctor')[0],503)
        finally:self.command('resume')

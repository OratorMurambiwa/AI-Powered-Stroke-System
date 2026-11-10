import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from uuid import uuid4
from wsgiref.simple_server import make_server

from clinical_api.app import ClinicalApplication
from clinical_api.__main__ import PrivateHandler
from clinical_api.identity import IdentityAdapter
from clinical_api.errors import ClinicalError
from clinical_api.linkage import LinkOperator
from clinical_api.source import ClinicalSource
from clinical_api.store import LinkStore
from clinical_api.service import ClinicalService
from clinical_api.validation import ISSUER
from clinical_api.tests.fixtures import create_records

ROOT = Path(__file__).parents[2]

class ClinicalIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uri = os.environ.get('TEST_MONGODB_URI', '')
        if uri != 'mongodb://stroke-booking-mongo:27017/synthetic_booking_test?replicaSet=rs0':
            raise RuntimeError('Real integration tests require the dedicated private Docker fixture')
        environment = dict(os.environ, MONGODB_URI=uri.replace('synthetic_booking_test', 'synthetic_clinical_identity'))
        # No signing/delivery key is passed to Python. Child creates both privately.
        cls.authority = subprocess.Popen(['node', 'test/clinical-authority-fixture.cjs'], cwd=ROOT / 'booking-backend',
            env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        raw = cls.authority.stdout.readline()
        if not raw:
            raise RuntimeError('Synthetic authority did not become ready')
        fixture = json.loads(raw)
        cls.port, cls.users = fixture['port'], fixture['users']
        cls.url = f'http://127.0.0.1:{cls.port}/api/v1/identity/clinical-introspect'

    @classmethod
    def tearDownClass(cls):
        if cls.authority.poll() is None:
            cls.authority.stdin.write('{"action":"stop"}\n')
            cls.authority.stdin.flush()
        try:
            cls.authority.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            cls.authority.kill()
            cls.authority.communicate()
            raise AssertionError('Synthetic authority did not stop')
        if cls.authority.returncode != 0:
            raise AssertionError('Synthetic authority exited unsuccessfully')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='stroke-clinical-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source_id = str(uuid4())
        self.records = self.directory / 'synthetic-records.sqlite'
        self.links = self.directory / 'synthetic-links.sqlite'
        create_records(self.records, self.source_id)
        self.original_source_hash = hashlib.sha256(self.records.read_bytes()).hexdigest()
        self.source = ClinicalSource(self.records, self.source_id)
        self.store = LinkStore(self.links, self.source_id)
        self.store.initialize()
        self.adapter = IdentityAdapter(self.url)
        self.manager = LinkOperator(self.store, self.source, self.adapter)
        self.service = ClinicalService(self.adapter, self.store, self.source)
        self.httpd = make_server('127.0.0.1', 0, ClinicalApplication(self.service), handler_class=PrivateHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.people = {role: self.register_person(role, native) for role, native in [('patient', 1), ('doctor', 1), ('technician', 2)]}
        self.patient_b = self.register_person('patient', 2)
        self.encounters = [self.register_encounter(self.people['patient'], 1), self.register_encounter(self.patient_b, 2), self.register_encounter(self.people['patient'], 3)]
        self.mapping = {
            'patientA': self.link('patientA', self.people['patient']),
            'patientB': self.link('patientB', self.patient_b),
            'doctor': self.link('doctor', self.people['doctor']),
            'technician': self.link('technician', self.people['technician']),
        }

    def tearDown(self):
        if self.records.exists():
            self.assertEqual(hashlib.sha256(self.records.read_bytes()).hexdigest(), self.original_source_hash)

    def close_server(self):
        self.httpd.shutdown()
        self.thread.join(timeout=3)
        self.httpd.server_close()

    def bearer(self, user):
        return 'Bearer ' + self.users[user]['token']

    def register_person(self, role, record):
        return self.manager.register_person({'schemaVersion': 1, 'sourceId': self.source_id, 'role': role, 'recordId': record}, 'synthetic-operator', 'SYNTHETIC independent record approval')['personId']

    def register_encounter(self, patient_id, record):
        return self.manager.register_encounter({'schemaVersion': 1, 'sourceId': self.source_id, 'patientId': patient_id, 'recordId': record}, 'synthetic-operator', 'SYNTHETIC encounter approval')['encounterId']

    def link(self, user, person_id, **overrides):
        command = {'schemaVersion': 1, 'issuer': ISSUER, 'subject': self.users[user]['id'], 'role': self.users[user]['role'], 'personId': person_id, **overrides}
        return self.manager.link(command, self.bearer(user), 'synthetic-operator', 'SYNTHETIC independent identity proof')

    def assign(self, user, encounter=None):
        return self.manager.assign({'schemaVersion': 1, 'mappingId': self.mapping[user]['mappingId'], 'encounterId': encounter or self.encounters[0]}, self.bearer(user), 'synthetic-operator', 'SYNTHETIC encounter assignment')

    def request(self, path, user=None, *, method='GET', headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port, timeout=5)
        try:
            request_headers = {'Authorization': self.bearer(user)} if user else {}
            request_headers.update(headers or {})
            connection.request(method, path, headers=request_headers)
            response = connection.getresponse()
            result = json.loads(response.read())
            return response.status, result, dict(response.getheaders())
        finally:
            connection.close()

    def authority_request(self, path, user, body, method='POST'):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            connection.request(method, '/api/v1/identity/' + path, json.dumps(body), {'Authorization': self.bearer(user), 'Content-Type': 'application/json'})
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
        finally:
            connection.close()

    def command(self, action, **fields):
        self.authority.stdin.write(json.dumps({'action': action, **fields}) + '\n')
        self.authority.stdin.flush()
        return json.loads(self.authority.stdout.readline())

    def assert_denied(self, callback, status):
        with self.assertRaises(ClinicalError) as error:
            callback()
        self.assertEqual(error.exception.status, status)

    def test_patient_linkage_owns_only_explicit_record(self):
        status, body, headers = self.request('/api/v1/clinical/patients/' + self.people['patient'], 'patientA')
        self.assertEqual(status, 200)
        self.assertEqual(body['demographics']['name'], 'Synthetic Patient A')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(self.request('/api/v1/clinical/patients/' + self.patient_b, 'patientA')[0], 404)
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[1], 'patientA')[0], 404)
        status, body, _ = self.request('/api/v1/clinical/patients/' + self.people['patient'] + '/encounters', 'patientA')
        self.assertEqual(status, 200)
        self.assertEqual({row['encounterId'] for row in body['encounters']}, {self.encounters[0], self.encounters[2]})

    def test_assigned_doctor_and_technician_have_encounter_scoped_access(self):
        for user in ('doctor', 'technician'):
            self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], user)[0], 404)
            self.assign(user)
            status, body, _ = self.request('/api/v1/clinical/encounters/' + self.encounters[0], user)
            self.assertEqual(status, 200)
            self.assertTrue(body['experimental'] and body['clinicianReviewRequired'])
            self.assertNotIn('scan_path', body['encounter'])
            self.assertNotIn('treatment_plan', body['encounter'])
            for other in self.encounters[1:]:
                self.assertEqual(self.request('/api/v1/clinical/encounters/' + other, user)[0], 404)
            self.assertEqual(self.request('/api/v1/clinical/patients/' + self.people['patient'], user)[0], 403)

    def test_admin_and_unmapped_users_have_no_clinical_access(self):
        for user in ('admin', 'unmapped', 'otherDoctor', 'otherTech'):
            self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], user)[0], 403)
        self.assert_denied(lambda: self.link('admin', self.people['patient']), 403)
        self.assertEqual(self.request('/api/v1/clinical/linkages', 'admin', method='POST')[0], 405)

    def test_duplicate_subject_or_patient_conflicts_without_relinking(self):
        self.assert_denied(lambda: self.link('patientA', self.people['patient']), 409)
        self.assert_denied(lambda: self.link('patientA', self.patient_b), 409)
        self.assert_denied(lambda: self.link('unmapped', self.people['patient']), 409)
        self.assertEqual(self.request('/api/v1/clinical/patients/' + self.people['patient'], 'patientA')[0], 200)

    def test_wrong_proof_role_or_source_and_name_matching_are_rejected(self):
        self.assert_denied(lambda: self.link('patientA', self.people['doctor']), 409)
        self.assert_denied(lambda: self.link('patientA', self.people['patient'], subject=self.users['patientB']['id']), 409)
        self.assert_denied(lambda: self.link('patientA', self.people['patient'], email='patienta@example.test'), 400)
        self.assert_denied(lambda: self.link('patientA', self.people['patient'], patientCode='P001'), 400)
        self.assert_denied(lambda: self.link('patientA', self.people['patient'], schemaVersion=2), 400)
        self.assert_denied(lambda: self.manager.register_person({'schemaVersion': 1, 'sourceId': str(uuid4()), 'role': 'patient', 'recordId': 1}, 'operator', 'SYNTHETIC'), 409)
        self.assert_denied(lambda: self.register_person('technician', 1), 409)
        self.assert_denied(lambda: self.register_encounter(self.patient_b, 1), 409)
        self.assert_denied(lambda: self.register_person('patient', 99), 404)

    def test_duplicate_concurrent_links_admit_one_explicit_mapping(self):
        self.manager.revoke({'schemaVersion': 1, 'id': self.mapping['patientA']['mappingId']}, 'operator', 'SYNTHETIC unlink')
        def create():
            try:
                self.link('patientA', self.people['patient'])
                return 201
            except ClinicalError as error:
                return error.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(lambda _: create(), range(2))), [201, 409])

    def test_assignment_and_mapping_revocation_take_effect_on_next_request(self):
        assignment = self.assign('doctor')
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'doctor')[0], 200)
        self.manager.revoke({'schemaVersion': 1, 'id': assignment['assignmentId']}, 'operator', 'SYNTHETIC remove assignment', assignment=True)
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'doctor')[0], 404)
        self.assign('doctor')
        self.manager.revoke({'schemaVersion': 1, 'id': self.mapping['doctor']['mappingId']}, 'operator', 'SYNTHETIC unlink')
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'doctor')[0], 403)
        self.mapping['doctor'] = self.link('doctor', self.people['doctor'])
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'doctor')[0], 404)
        self.assign('doctor')
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'doctor')[0], 200)

    def test_missing_or_conflicting_assignments_are_not_inferred(self):
        self.assert_denied(lambda: self.assign('patientA'), 403)
        self.assert_denied(lambda: self.assign('doctor', str(uuid4())), 404)
        self.assign('doctor')
        self.assert_denied(lambda: self.assign('doctor'), 409)
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[1], 'doctor')[0], 404)

    def test_live_authority_outage_fails_closed_then_recovers_without_relink(self):
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'patientA')[0], 200)
        self.command('pause')
        try:
            self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'patientA')[0], 503)
            self.assert_denied(lambda: self.link('unmapped', self.patient_b), 503)
        finally:
            self.command('resume')
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'patientA')[0], 200)

    def test_mapping_and_source_failures_recover_without_corrupting_links(self):
        for path in (self.links, self.records):
            moved = path.with_suffix('.offline')
            path.rename(moved)
            try:
                self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'patientA')[0], 503)
                self.assertFalse(path.exists())
            finally:
                moved.rename(path)
            self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'patientA')[0], 200)

    def test_mapping_audit_failure_rolls_back_link_and_assignment(self):
        self.manager.revoke({'schemaVersion': 1, 'id': self.mapping['patientA']['mappingId']}, 'operator', 'SYNTHETIC unlink')
        with self.store.connection(write=True) as db:
            db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT,'synthetic audit failure'); END")
        self.assert_denied(lambda: self.link('patientA', self.people['patient']), 409)
        self.assert_denied(lambda: self.assign('doctor'), 409)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM assignments').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM identity_links WHERE revoked_at IS NULL').fetchone()[0], 3)
        with self.store.connection(write=True) as db:
            db.execute('DROP TRIGGER fail_audit')
        self.link('patientA', self.people['patient'])
        self.assign('doctor')
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'doctor')[0], 200)

    def test_ids_persist_across_store_reopen_and_audits_have_no_credentials(self):
        reopened = LinkStore(self.links, self.source_id)
        with reopened.connection() as db:
            mapping = dict(db.execute('SELECT * FROM identity_links WHERE id=?', (self.mapping['patientA']['mappingId'],)).fetchone())
            events = [dict(row) for row in db.execute('SELECT * FROM audit')]
        self.assertEqual(mapping['person_id'], self.people['patient'])
        self.assertEqual(mapping['subject'], self.users['patientA']['id'])
        contract = json.loads((ROOT / 'clinical_api/contracts/mapping-receipt-v1.schema.json').read_text())
        self.assertEqual(set(self.mapping['patientA']), set(contract['required']))
        self.assertEqual(self.mapping['patientA']['schemaVersion'], 1)
        self.assertIn(self.mapping['patientA']['role'], contract['properties']['role']['enum'])

        raw = json.dumps(events)
        for user in self.users.values():
            self.assertNotIn(user['token'], raw)
            self.assertNotIn(user['password'], raw)
            self.assertNotIn(user['email'], raw)
        self.assertIn('IDENTITY_LINKED', raw)
        with self.assertRaises(FileExistsError):
            reopened.initialize()

    def test_source_mismatch_and_wrong_mapping_version_fail_closed(self):
        self.service.source = ClinicalSource(self.records, str(uuid4()))
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'patientA')[0], 503)
        self.service.source = self.source
        self.service.store = LinkStore(self.links, str(uuid4()))
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'patientA')[0], 503)
        self.service.store = self.store
        db = sqlite3.connect(self.links)
        db.execute('PRAGMA ignore_check_constraints=ON')
        db.execute('UPDATE metadata SET version=2')
        db.commit()
        db.close()
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'patientA')[0], 503)


    def test_reused_native_primary_key_with_new_record_uuid_cannot_inherit_access(self):
        original = self.records.read_bytes()
        db = sqlite3.connect(self.records)
        try:
            db.execute("UPDATE clinical_record_ids SET record_uuid=? WHERE kind='patient' AND native_id=1", (str(uuid4()),))
            db.commit()
        finally:
            db.close()
        try:
            self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'patientA')[0], 503)
            self.assert_denied(lambda: self.link('patientA', self.people['patient']), 409)
        finally:
            self.records.write_bytes(original)  # Restore only this freshly generated fault fixture.
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'patientA')[0], 200)

    def test_legacy_sessions_headers_and_sql_injection_grant_no_access(self):
        target = '/api/v1/clinical/encounters/' + self.encounters[0]
        self.assertEqual(self.request(target, headers={'Cookie': 'streamlit_user=doctor', 'X-User-Role': 'admin'})[0], 401)
        self.assertEqual(self.request(target, 'patientA', headers={'X-User-Role': 'admin'})[0], 200)
        self.assertEqual(self.request('/api/v1/clinical/patients/1', 'patientA')[0], 400)
        self.assertEqual(self.request(target + '?patientId=' + self.patient_b, 'patientA')[0], 400)
        self.assertEqual(self.request('/api/v1/clinical/patients/1%27OR%271=1', 'patientA')[0], 400)
        self.assertEqual(self.request(target, 'admin', method='PUT')[0], 405)

    def test_z_revocation_expiration_and_role_epoch_require_fresh_authorization(self):
        # Mutates only synthetic authority users, last scenario in this class.
        self.assign('doctor')
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'doctor')[0], 200)
        admin = self.users['admin']
        role_path = f"staff/{self.users['doctor']['id']}/role"
        for role in ('technician', 'doctor'):
            status, _ = self.authority_request(role_path, 'admin', {'role': role, 'reason': 'SYNTHETIC role epoch regression', 'currentPassword': admin['password']}, 'PATCH')
            self.assertEqual(status, 200)
        status, logged = self.authority_request('auth/login', 'doctor', {'email': self.users['doctor']['email'], 'password': self.users['doctor']['password']})
        self.assertEqual(status, 200)
        self.users['doctor']['token'] = logged['token']
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'doctor')[0], 403)
        self.manager.revoke({'schemaVersion': 1, 'id': self.mapping['doctor']['mappingId']}, 'operator', 'SYNTHETIC new role approval')
        self.mapping['doctor'] = self.link('doctor', self.people['doctor'])
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'doctor')[0], 404)
        self.assign('doctor')
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'doctor')[0], 200)
        status, _ = self.authority_request(f"staff/{self.users['doctor']['id']}/revoke", 'admin', {'reason': 'SYNTHETIC offboarding', 'currentPassword': admin['password']})
        self.assertEqual(status, 200)
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'doctor')[0], 401)
        self.command('expire', user='patientB')
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[1], 'patientB')[0], 401)
        self.assertEqual(self.authority_request('auth/logout', 'patientA', {})[0], 204)
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'patientA')[0], 401)
        status, logged = self.authority_request('auth/login', 'patientA', {'email': self.users['patientA']['email'], 'password': self.users['patientA']['password']})
        self.assertEqual(status, 200)
        self.users['patientA']['token'] = logged['token']
        self.assertEqual(self.request('/api/v1/clinical/encounters/' + self.encounters[0], 'patientA')[0], 200)

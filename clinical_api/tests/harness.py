import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import selectors
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from uuid import uuid4
from wsgiref.simple_server import make_server

from clinical_api.app import ClinicalApplication
from clinical_api.__main__ import PrivateHandler, LocalClinicalServer
from clinical_api.identity import IdentityAdapter
from clinical_api.errors import ClinicalError
from clinical_api.linkage import LinkOperator
from clinical_api.source import ClinicalSource
from clinical_api.store import LinkStore
from clinical_api.service import ClinicalService
from clinical_api.validation import ISSUER
from clinical_api.tests.fixtures import create_records

ROOT = Path(__file__).parents[2]

class ClinicalFixture:
    database = "synthetic_clinical_identity"
    store_version = 1

    @classmethod
    def setUpClass(cls):
        uri = os.environ.get('TEST_MONGODB_URI', '')
        if uri != 'mongodb://stroke-booking-mongo:27017/synthetic_booking_test?replicaSet=rs0':
            raise RuntimeError('Real integration tests require the dedicated private Docker fixture')
        environment = dict(os.environ, MONGODB_URI=uri.replace('synthetic_booking_test', cls.database))
        # No signing/delivery key is passed to Python. Child creates both privately.
        cls.authority = subprocess.Popen(['node', 'test/clinical-authority-fixture.cjs'], cwd=ROOT / 'booking-backend',
            env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        with selectors.DefaultSelector() as selector:
            selector.register(cls.authority.stdout, selectors.EVENT_READ)
            ready = bool(selector.select(timeout=30))
        raw = cls.authority.stdout.readline(32768) if ready else ''
        if not raw:
            cls.authority.kill()
            cls.authority.communicate(timeout=5)
            raise RuntimeError('Synthetic authority did not become ready within the bounded startup window')
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
        self.store = LinkStore(self.links, self.source_id, self.store_version)
        self.store.initialize()
        self.adapter = IdentityAdapter(self.url)
        self.manager = LinkOperator(self.store, self.source, self.adapter)
        self.service = ClinicalService(self.adapter, self.store, self.source)
        self.httpd = make_server('127.0.0.1', 0, ClinicalApplication(self.service), handler_class=PrivateHandler, server_class=LocalClinicalServer)
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

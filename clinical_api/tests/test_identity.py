import base64
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from uuid import uuid4
from unittest.mock import patch

from clinical_api.config import Config
from clinical_api.identity import IdentityAdapter
from clinical_api.errors import ClinicalError
from clinical_api.validation import ISSUER, strict_json
from clinical_api.source import ClinicalSource
from clinical_api.store import LinkStore

class IdentityTransportTests(unittest.TestCase):
    def setUp(self):
        self.subject = 'a' * 24
        self.sid = str(uuid4())
        self.expiry = int(time.time()) + 600
        claims = {'iss': ISSUER, 'aud': 'urn:stroke-platform:booking:v1', 'ver': 1, 'sub': self.subject, 'sid': self.sid, 'exp': self.expiry}
        encode = lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
        self.token = encode({'alg': 'HS256', 'typ': 'JWT'}) + '.' + encode(claims) + '.synthetic-signature'
        self.body = {'active': True, 'schemaVersion': 1, 'issuer': ISSUER, 'subject': self.subject, 'role': 'patient',
                     'sessionId': self.sid, 'expiresAt': self.expiry, 'roleVersion': 0}
        self.status = 200
        self.raw = None
        self.content_type = 'application/json'
        self.delay = 0
        self.redirect = None
        self.requests = []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_POST(self):
                owner.requests.append((self.path, self.headers.get('Authorization'), self.rfile.read(int(self.headers.get('Content-Length', 0)))))
                if owner.delay:
                    time.sleep(owner.delay)
                raw = owner.raw if owner.raw is not None else json.dumps(owner.body).encode()
                self.send_response(owner.status)
                self.send_header('Content-Type', owner.content_type)
                self.send_header('Content-Length', str(len(raw)))
                if owner.redirect:
                    self.send_header('Location', owner.redirect)
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        self.httpd = HTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.httpd.server_port}/api/v1/identity/clinical-introspect'
        self.adapter = IdentityAdapter(self.url, timeout=0.1)

    def tearDown(self):
        self.httpd.shutdown()
        self.thread.join(2)
        self.httpd.server_close()

    def denied(self, expected=503, bearer=None):
        with self.assertRaises(ClinicalError) as error:
            self.adapter.introspect(bearer or 'Bearer ' + self.token)
        self.assertEqual(error.exception.status, expected)
        self.assertNotIn(self.token, str(error.exception))

    def test_success_is_live_and_proxies_are_disabled(self):
        with patch.dict('os.environ', {'HTTP_PROXY': 'http://127.0.0.1:1', 'HTTPS_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': ''}):
            adapter = IdentityAdapter(self.url)
            self.assertEqual(adapter.introspect('Bearer ' + self.token).subject, self.subject)
            self.assertEqual(adapter.introspect('Bearer ' + self.token).role, 'patient')
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.requests[0], ('/api/v1/identity/clinical-introspect', 'Bearer ' + self.token, b'{}'))

    def test_invalid_session_status_and_service_failure_fail_closed(self):
        for status, expected in [(401, 401), (403, 401), (404, 503), (429, 503), (500, 503), (503, 503)]:
            with self.subTest(status=status):
                self.status = status
                self.denied(expected)
        self.status = 200
        self.assertEqual(self.adapter.introspect('Bearer ' + self.token).subject, self.subject)

    def test_malformed_json_duplicate_fields_and_large_response_are_rejected(self):
        for raw in [b'not-json', b'[]', b'null', b'{"active":true,"active":false}', b'{"active":NaN}', b'\xff', b' ' * 4097, b'[' * 1100 + b'0' + b']' * 1100]:
            with self.subTest(raw_kind=raw[:15]):
                self.raw = raw
                self.denied()

    def test_closed_contract_rejects_wrong_types_roles_version_and_extra_keys(self):
        baseline = dict(self.body)
        for key, value in [('active', False), ('schemaVersion', 2), ('schemaVersion', True), ('issuer', 'other'), ('role', 'physician'),
                           ('role', ['patient']), ('subject', 'BAD'), ('sessionId', 'BAD'), ('expiresAt', True), ('roleVersion', -1), ('roleVersion', True), ('extra', 'ignored')]:
            with self.subTest(key=key, value=value):
                self.body = {**baseline, key: value}
                self.denied()
        self.body = {key: value for key, value in baseline.items() if key != 'roleVersion'}
        self.denied()

    def test_expired_overlong_or_misbound_identity_responses_are_rejected(self):
        baseline = dict(self.body)
        for field, value in [('expiresAt', int(time.time()) - 1), ('expiresAt', int(time.time()) + 10000), ('subject', 'b' * 24), ('sessionId', str(uuid4()))]:
            with self.subTest(field=field):
                self.body = {**baseline, field: value}
                self.denied()

    def test_redirects_do_not_forward_bearer_and_bad_content_type_is_rejected(self):
        self.status = 307
        self.redirect = self.url + '/should-not-follow'
        self.denied()
        self.assertEqual(len(self.requests), 1)
        self.status = 200
        self.content_type = 'text/html'
        self.denied()

    def test_timeout_then_recovery_does_not_cache_success(self):
        self.delay = 0.2
        self.denied()
        self.delay = 0
        time.sleep(0.25)
        self.assertEqual(self.adapter.introspect('Bearer ' + self.token).subject, self.subject)
        self.status = 401
        self.denied(401)

    def test_missing_malformed_oversized_tokens_never_authenticate_locally(self):
        for bearer in ['Basic abc', 'Bearer legacy-session', 'Bearer a.b.c', 'Bearer ' + 'a' * 5000]:
            with self.subTest(kind=bearer[:20]):
                self.denied(401, bearer)
        self.assertEqual(self.requests, [])

    def test_only_explicit_local_canonical_url_and_bounded_timeout_are_allowed(self):
        for url in ['http://example.com/api/v1/identity/clinical-introspect', self.url + '?redirect=1', self.url + '#secret', self.url.replace('127.0.0.1', 'user:password@127.0.0.1'), self.url.replace('/clinical-introspect', '/introspect')]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                IdentityAdapter(url)
        for timeout in [0, 6, float('nan')]:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                IdentityAdapter(self.url, timeout)

class ConfigurationTests(unittest.TestCase):
    def test_no_implicit_database_or_dotenv_configuration(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(ValueError):
            Config.from_environment()
        with patch.dict('os.environ', {'CLINICAL_DATA_MODE': 'synthetic'}, clear=True), self.assertRaises(KeyError):
            Config.from_environment()

    def test_missing_read_only_source_or_mapping_store_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'absent.sqlite'
            for store in [LinkStore(path, str(uuid4())), ClinicalSource(path, str(uuid4()))]:
                with self.subTest(store=type(store).__name__), self.assertRaises(ClinicalError):
                    with store.connection():
                        pass
                self.assertFalse(path.exists())

    def test_stores_cannot_alias_and_unmarked_legacy_schema_is_refused(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic-unmarked.sqlite'
            sqlite3.connect(path).close()
            with self.assertRaises(ClinicalError):
                with ClinicalSource(path, str(uuid4())).connection():
                    pass
            with self.assertRaises(ValueError):
                Config(path, path, str(uuid4()), 'http://127.0.0.1:1/api/v1/identity/clinical-introspect').service()

    def test_v2_store_cannot_silently_adopt_or_overwrite_v1(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'new-synthetic-links.sqlite'
            source_id=str(uuid4())
            LinkStore(path,source_id).initialize()
            original=hashlib.sha256(path.read_bytes()).hexdigest()
            upgraded=LinkStore(path,source_id,2)
            with self.assertRaises(FileExistsError):
                upgraded.initialize()
            with self.assertRaises(ClinicalError):
                with upgraded.connection(write=True):
                    pass
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),original)

    def test_json_contract_parser_rejects_duplicate_or_nonfinite_fields(self):
        for raw in [b'{"schemaVersion":1,"schemaVersion":2}', b'{"x":NaN}']:
            with self.assertRaises(ValueError):
                strict_json(raw)

class OperatorBoundaryTests(unittest.TestCase):
    def test_proof_token_requires_private_interactive_terminal(self):
        from clinical_api.operator import main
        from clinical_api.identity import Principal
        from clinical_api.service import ClinicalService
        from clinical_api.tests.fixtures import create_records
        from clinical_api.validation import ISSUER
        with tempfile.TemporaryDirectory() as directory:
            source_id = str(uuid4())
            records = Path(directory) / 'synthetic.sqlite'
            links = Path(directory) / 'links.sqlite'
            create_records(records, source_id)
            config = Config(records, links, source_id, 'http://127.0.0.1:1/api/v1/identity/clinical-introspect')
            command = json.dumps({'schemaVersion': 1, 'issuer': ISSUER, 'subject': 'a' * 24, 'role': 'patient', 'personId': str(uuid4())})
            with patch('clinical_api.operator.Config.from_environment', return_value=config), patch('sys.argv', ['operator', 'link']), patch('builtins.input', side_effect=['synthetic-operator', 'SYNTHETIC approval', command]), patch('sys.stdin.isatty', return_value=False), patch('getpass.getpass') as prompt:
                with self.assertRaises(ClinicalError) as error:
                    main()
                self.assertEqual(error.exception.code, 'private_terminal_required')
                prompt.assert_not_called()

class BookingProofTests(unittest.TestCase):
    # Reuse only the local HTTP fixture, not its test methods.
    setUp = IdentityTransportTests.setUp
    tearDown = IdentityTransportTests.tearDown

    def prepare(self):
        from clinical_api.identity import Principal
        from clinical_api.booking import BookingAdapter
        self.appointment_id, self.request_id, self.encounter_id = str(uuid4()), str(uuid4()), str(uuid4())
        self.command_hash = 'a' * 64
        self.principal = Principal(ISSUER,self.subject,'doctor',self.sid,self.expiry,0)
        self.body = {'schemaVersion':1,'issuer':ISSUER,'appointmentId':self.appointment_id,'requestId':self.request_id,
                     'encounterId':self.encounter_id,'commandHash':self.command_hash,'patientSubject':'b'*24,'patientRoleVersion':0,
                     'doctorSubject':self.subject,'doctorRoleVersion':0,'actorSubject':self.subject,'actorRoleVersion':0,
                     'sessionId':self.sid,'status':'RESERVED','expiresAt':int(time.time())+60}
        self.booking = BookingAdapter(self.adapter)

    def proof(self):
        return self.booking.proof('Bearer '+self.token,self.principal,self.appointment_id,self.request_id,self.command_hash,self.encounter_id)

    def test_live_proof_binds_actor_command_and_exact_appointment(self):
        self.prepare()
        self.assertEqual(self.proof(),self.body)
        self.assertEqual(self.requests[0][0],f'/api/v1/appointments/{self.appointment_id}/assessment-proof')
        self.assertEqual(json.loads(self.requests[0][2]),{'schemaVersion':1,'requestId':self.request_id})

    def test_malformed_stale_misbound_or_cancelled_proof_fails_closed(self):
        self.prepare(); baseline=dict(self.body)
        for field,value in [('schemaVersion',True),('issuer','wrong'),('status','cancelled'),('actorSubject','c'*24),
                           ('patientSubject','invalid'),('doctorSubject','c'*24),('doctorRoleVersion',1),('actorRoleVersion',False),
                           ('sessionId',str(uuid4())),('requestId',str(uuid4())),('encounterId',str(uuid4())),('commandHash','b'*64),
                           ('expiresAt',int(time.time())-1),('expiresAt',int(time.time())+120),('extra','field')]:
            self.body={**baseline,field:value}
            with self.subTest(field=field), self.assertRaises(ClinicalError) as error:
                self.proof()
            self.assertEqual(error.exception.status,503)

    def test_authority_rejection_outage_and_redirect_do_not_allow_creation(self):
        self.prepare()
        for status,expected in [(401,401),(403,401),(404,409),(409,409),(500,503),(307,503)]:
            self.status=status
            self.redirect=self.url+'/not-followed' if status==307 else None
            with self.subTest(status=status), self.assertRaises(ClinicalError) as error:
                self.proof()
            self.assertEqual(error.exception.status,expected)
        self.status=200;self.redirect=None
        self.assertEqual(self.proof()['status'],'RESERVED')

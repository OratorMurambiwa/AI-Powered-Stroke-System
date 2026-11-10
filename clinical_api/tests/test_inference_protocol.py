"""Controlled protocol responses only; actual inference is tested separately."""
import hashlib
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from clinical_api.errors import ClinicalError
from clinical_api.inference import InferenceAdapter, MODEL_SHA256,MODEL_VERSION,PREPROCESS_VERSION

class InferenceProtocol(unittest.TestCase):
    def setUp(self):
        self.raw=b'synthetic-protocol-payload'
        self.sha=hashlib.sha256(self.raw).hexdigest()
        self.payload={'schemaVersion':1,'predictedClass':'normal','rawScore':0.5,'scores':[0.2,0.3,0.5],
            'modelSha256':MODEL_SHA256,'modelVersion':MODEL_VERSION,'preprocessingVersion':PREPROCESS_VERSION,
            'scanSha256':self.sha,'durationMs':1}
        self.status=200; self.redirect=False; self.calls=0; self.body=None
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_POST(self):
                owner.calls+=1
                self.rfile.read(int(self.headers['Content-Length']))
                body=owner.body if owner.body is not None else json.dumps(owner.payload).encode()
                self.send_response(owner.status)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(body)))
                if owner.redirect: self.send_header('Location',f'http://127.0.0.1:{owner.server.server_port}/api/v1/predict')
                self.end_headers(); self.wfile.write(body)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/api/v1/predict'
        self.adapter=InferenceAdapter(self.url,'4'*64)
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown(); self.thread.join(timeout=3); self.server.server_close()

    def denied(self):
        with self.assertRaises(ClinicalError) as error:
            self.adapter.predict(self.raw,self.sha)
        self.assertEqual(error.exception.status,503)

    def test_strict_valid_contract_is_bound_to_supplied_input(self):
        self.assertEqual(self.adapter.predict(self.raw,self.sha),self.payload)
        with self.assertRaises(ClinicalError):
            self.adapter.predict(self.raw,'0'*64)
        self.assertEqual(self.calls,1)

    def test_model_input_version_and_label_mismatches_fail_closed(self):
        original=dict(self.payload)
        for changes in [{'modelSha256':'0'*64},{'scanSha256':'0'*64},{'modelVersion':'other'},
                        {'preprocessingVersion':'other'},{'predictedClass':'bleeding'},{'schemaVersion':True},
                        {'path':'/etc/passwd'}]:
            self.payload={**original,**changes}; self.denied()

    def test_nonfinite_inconsistent_and_boolean_scores_are_rejected(self):
        original=dict(self.payload)
        for changes in [{'scores':[0.2,0.3,float('nan')]},{'scores':[0.2,0.3,True]},
                        {'scores':[0.2,0.3,0.4]},{'rawScore':True},{'rawScore':0.7},
                        {'durationMs':float('inf')},{'durationMs':20001}]:
            self.payload={**original,**changes}; self.denied()

    def test_redirect_error_oversize_and_malformed_responses_recover(self):
        self.status=302; self.redirect=True; self.denied(); self.assertEqual(self.calls,1)
        self.redirect=False; self.status=503; self.denied()
        self.status=200
        for raw in [b'{}',b'{"schemaVersion":1,"schemaVersion":1}',b'x'*4097,b'<html>no</html>']:
            self.body=raw; self.denied()
        self.body=None
        self.assertEqual(self.adapter.predict(self.raw,self.sha),self.payload)

    def test_only_explicit_private_endpoint_and_nondefault_key_are_allowed(self):
        for url,key in [('https://example.com/api/v1/predict','4'*64),(self.url+'?url=x','4'*64),
                        (self.url,'default'),(self.url.replace('/predict','/other'),'4'*64),
                        (self.url.replace('127.0.0.1','user:password@127.0.0.1'),'4'*64)]:
            with self.assertRaises(ValueError):
                InferenceAdapter(url,key)

"""Real private HTTP service, real CPU inference, bounded owned-process faults."""
import base64,hashlib,json,os,secrets,signal,socket,subprocess,sys,time,unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from inference_worker.server import synthetic
from inference_worker.model import MODEL_SHA256

class WorkerTransport(unittest.TestCase):
    @classmethod
    def start(cls):
        cls.key=secrets.token_hex(32)
        cls.process=subprocess.Popen([sys.executable,'-m','inference_worker.server'],env={**os.environ,'INFERENCE_SERVICE_KEY':cls.key},
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        deadline=time.monotonic()+75
        while time.monotonic()<deadline:
            if cls.process.poll() is not None:raise AssertionError('real worker startup failed')
            try:
                if cls.http('/health')[0]==200:return
            except OSError:pass
            time.sleep(.1)
        cls.stop();raise AssertionError('worker readiness deadline')
    @classmethod
    def supervisor(cls):
        values=Path(f'/proc/{cls.process.pid}/task/{cls.process.pid}/children').read_text().split()
        if len(values)!=1:raise AssertionError('expected one owned model supervisor')
        return int(values[0])
    @classmethod
    def stop(cls):
        if cls.process.poll() is None:
            try:os.killpg(cls.supervisor(),signal.SIGKILL)
            except (ProcessLookupError,AssertionError):pass
            cls.process.terminate()
        cls.process.wait(timeout=5)
    @classmethod
    def setUpClass(cls):cls.start()
    @classmethod
    def tearDownClass(cls):cls.stop()
    @classmethod
    def http(cls,path,command=None,key=None):
        req=Request('http://127.0.0.1:8020'+path,data=json.dumps(command).encode() if command is not None else None,
            headers={'Content-Type':'application/json','Authorization':'Bearer '+(cls.key if key is None else key)})
        try:
            with urlopen(req,timeout=25) as response:return response.status,json.loads(response.read(4097))
        except HTTPError as error:
            with error:return error.code,json.loads(error.read(4097))
    def job(self):return {'schemaVersion':1,**synthetic(),'modelSha256':MODEL_SHA256}
    def test_concurrent_real_jobs_reject_busy_without_corrupting_results(self):
        from threading import Barrier
        barrier=Barrier(8)
        def send(_):barrier.wait(timeout=5);return self.http('/api/v1/predict',self.job())
        with ThreadPoolExecutor(max_workers=8) as executor:results=list(executor.map(send,range(8)))
        self.assertIn(200,[s for s,_ in results]);self.assertIn(429,[s for s,_ in results])
        for status,body in results:
            self.assertIn(status,{200,429})
            if status==200:self.assertEqual(body['scanSha256'],self.job()['scanSha256'])
        self.assertEqual(self.http('/api/v1/predict',self.job())[0],200)
    def test_forbidden_malicious_and_truncated_bodies_recover(self):
        self.assertEqual(self.http('/api/v1/predict',self.job(),key='invalid')[0],403)
        raw=b'<svg onload="alert(1)"/>'
        self.assertEqual(self.http('/api/v1/predict',{**self.job(),'contentBase64':base64.b64encode(raw).decode(),'scanSha256':hashlib.sha256(raw).hexdigest()})[0],400)
        with socket.create_connection(('127.0.0.1',8020),timeout=6) as connection:
            request=f'POST /api/v1/predict HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {self.key}\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{{'
            connection.sendall(request.encode());connection.shutdown(socket.SHUT_WR)
            self.assertIn(b'400',connection.recv(4096).split(b'\r\n')[0])
        self.assertEqual(self.http('/api/v1/predict',self.job())[0],200)
    def test_z_supervisor_death_fails_health_and_inference_then_restart_recovers(self):
        os.killpg(self.supervisor(),signal.SIGKILL)
        time.sleep(.1)
        self.assertEqual(self.http('/health')[0],503)
        self.assertEqual(self.http('/api/v1/predict',self.job())[0],503)
        type(self).stop();type(self).start()
        self.assertEqual(self.http('/api/v1/predict',self.job())[0],200)

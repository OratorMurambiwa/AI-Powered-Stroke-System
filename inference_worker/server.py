"""Private local transport, single admitted job, isolated bounded subprocess."""
import base64
import hashlib
import hmac
import json
import os
import signal
import struct
import subprocess
import sys
import threading
import zlib
import binascii
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .model import MODEL_SHA256


def run_job(command, timeout=20):
    environment={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','USER':'stroke-inference','LOGNAME':'stroke-inference','TORCHINDUCTOR_CACHE_DIR':'/tmp/torch','PYTHONPATH':'/app',
                 'YOLO_CONFIG_DIR':'/tmp/yolo','MPLCONFIGDIR':'/tmp/matplotlib','YOLO_AUTOINSTALL':'false',
                 'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2','CUDA_VISIBLE_DEVICES':'', 'PYTHONDONTWRITEBYTECODE':'1'}
    process=subprocess.Popen([sys.executable,'-m','inference_worker.child'],stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,cwd='/app',env=environment,start_new_session=True)
    try:
        output,_=process.communicate(json.dumps(command,separators=(',',':')).encode(),timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL)
        process.communicate()
        raise RuntimeError('inference_deadline') from None
    if process.returncode or not 1<=len(output)<=4096:
        raise RuntimeError('inference_failed')
    return json.loads(output)


def synthetic():
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',binascii.crc32(kind+data)&0xffffffff)
    raw=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',64,64,8,0,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x80'*64)*64))+chunk(b'IEND',b'')
    return {'contentBase64':base64.b64encode(raw).decode(),'scanSha256':hashlib.sha256(raw).hexdigest()}


def main():
    key=os.environ.get('INFERENCE_SERVICE_KEY','')
    if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('explicit_private_key_required')
    # Never accept requests until this exact artifact successfully executes on CPU.
    if run_job(synthetic())['modelSha256']!=MODEL_SHA256:
        raise RuntimeError('model_not_ready')
    admission=threading.BoundedSemaphore(1)
    def unique_pairs(pairs):
        value={}
        for name,item in pairs:
            if name in value:
                raise ValueError('duplicate_key')
            value[name]=item
        return value
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_args):
            pass
        def reply(self,status,value):
            raw=json.dumps(value,allow_nan=False).encode()
            self.send_response(status)
            for name,value in [('Content-Type','application/json'),('Content-Length',str(len(raw))),('Cache-Control','no-store')]:
                self.send_header(name,value)
            self.end_headers(); self.wfile.write(raw)
        def do_GET(self):
            if self.path=='/health':
                self.reply(200,{'schemaVersion':1,'modelSha256':MODEL_SHA256,'ready':True})
            else:
                self.reply(404,{'error':'not_found'})
        def do_POST(self):
            if self.path!='/api/v1/predict' or not hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+key):
                self.reply(403,{'error':'forbidden'}); return
            if not admission.acquire(blocking=False):
                self.reply(429,{'error':'worker_busy'}); return
            try:
                self.connection.settimeout(5)
                length=self.headers.get('Content-Length','')
                if len(self.headers.get_all('Content-Length',[]))!=1 or self.headers.get('Transfer-Encoding') or len(length)>7 or not length.isdigit() or not 1<=int(length)<=1400000 or self.headers.get('Content-Type')!='application/json':
                    self.reply(400,{'error':'invalid_job'}); return
                from clinical_api.errors import ClinicalError
                from clinical_api.png import validate_png
                raw=self.rfile.read(int(length))
                command=json.loads(raw,object_pairs_hook=unique_pairs)
                if set(command)!={'schemaVersion','contentBase64','scanSha256','modelSha256'} or type(command['schemaVersion']) is not int or command['schemaVersion']!=1 or command['modelSha256']!=MODEL_SHA256:
                    self.reply(400,{'error':'invalid_job'}); return
                image=base64.b64decode(command['contentBase64'],validate=True)
                validate_png(image)
                if hashlib.sha256(image).hexdigest()!=command['scanSha256']:
                    self.reply(400,{'error':'scan_hash_mismatch'}); return
                result=run_job(command)
                self.reply(200,{'schemaVersion':1,**result})
            except (ValueError,KeyError,TypeError,ClinicalError):
                self.reply(400,{'error':'invalid_job'})
            except Exception:
                self.reply(503,{'error':'inference_unavailable'})
            finally:
                admission.release()
    ThreadingHTTPServer(('0.0.0.0',8020),Handler).serve_forever()

if __name__=='__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Inference worker startup refused') from None

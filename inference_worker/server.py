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


def child_environment():
    return {'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','USER':'stroke-inference','LOGNAME':'stroke-inference','TORCHINDUCTOR_CACHE_DIR':'/tmp/torch','PYTHONPATH':'/app',
                 'YOLO_CONFIG_DIR':'/tmp/yolo','MPLCONFIGDIR':'/tmp/matplotlib','YOLO_AUTOINSTALL':'false','YOLO_OFFLINE':'true',
                 'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2','CUDA_VISIBLE_DEVICES':'', 'PYTHONDONTWRITEBYTECODE':'1'}


_pool=None
_pool_child=None
_pool_broken=False

def close_pool():
    global _pool,_pool_child
    if _pool_child:
        try:os.killpg(_pool_child,signal.SIGKILL)
        except ProcessLookupError:pass
        _pool_child=None
    if _pool is not None:
        try:os.killpg(_pool.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        _pool.communicate(timeout=3)
        _pool=None

def _line(process,timeout):
    import selectors
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout,selectors.EVENT_READ)
        if not selector.select(timeout):raise RuntimeError('inference_deadline')
    raw=process.stdout.readline(8193)
    if not raw or len(raw)>8192:raise RuntimeError('inference_failed')
    return json.loads(raw)

def run_job(command, timeout=20):
    global _pool,_pool_child,_pool_broken
    if _pool_broken:raise RuntimeError('inference_failed')
    if _pool is None:
        _pool=subprocess.Popen([sys.executable,'-m','inference_worker.pool'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,cwd='/app',env=child_environment(),start_new_session=True,bufsize=0)
        try:
            if _line(_pool,60)!={'ready':True}:raise RuntimeError('inference_failed')
        except BaseException:
            close_pool();raise
    if _pool.poll() is not None:raise RuntimeError('inference_failed')
    try:
        payload=json.dumps({**command,'_deadline':timeout},separators=(',',':')).encode()+b'\n'
        if len(payload)>1400000:raise RuntimeError('inference_failed')
        # One admitted HTTP request at a time; the supervisor never receives secrets.
        view=memoryview(payload)
        while view:
            written=_pool.stdin.write(view)
            if not written:raise OSError('closed supervisor pipe')
            view=view[written:]
        started=_line(_pool,2)
        if set(started)!={'started'} or type(started['started']) is not int or started['started']<2:raise RuntimeError('inference_failed')
        _pool_child=started['started']
        reply=_line(_pool,timeout+2)
        _pool_child=None
    except (OSError,ValueError,KeyError,RuntimeError):
        _pool_broken=True;close_pool();raise RuntimeError('inference_failed') from None
    if 'error' in reply:
        raise RuntimeError(reply['error'] if reply['error'] in {'inference_deadline','inference_failed'} else 'inference_failed')
    return reply['result']


import atexit
atexit.register(close_pool)


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
    except Exception as error:
        code=str(error) if str(error) in {'inference_deadline','inference_failed','model_not_ready','explicit_private_key_required'} else 'startup_check_failed'
        raise SystemExit('Inference worker startup refused: '+code) from None

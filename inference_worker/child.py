"""One bounded CPU job; the parent kills this entire process group on deadline."""
import base64
import contextlib
import hashlib
import json
import os
import resource
import sys
import time


def main():
    resource.setrlimit(resource.RLIMIT_CPU,(12,12))
    resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
    # Container memory/cpu/pid limits are additional to this per-job limit.
    started=time.monotonic()
    raw=sys.stdin.buffer.read(1400001)
    if len(raw)>1400000:
        raise ValueError('invalid_job')
    request=json.loads(raw)
    image=base64.b64decode(request['contentBase64'],validate=True)
    if hashlib.sha256(image).hexdigest()!=request['scanSha256']:
        raise ValueError('scan_hash_mismatch')
    # Suppress library status output; never log input/image/model payloads.
    with open(os.devnull,'w') as sink, contextlib.redirect_stdout(sink):
        from .model import predict
        prediction=predict(image)
    prediction['scanSha256']=request['scanSha256']
    prediction['durationMs']=round((time.monotonic()-started)*1000,3)
    sys.stdout.write(json.dumps(prediction,allow_nan=False,separators=(',',':')))

if __name__=='__main__':
    try:
        main()
    except Exception:
        sys.exit(1)  # No traceback or image/private paths in logs/protocol.

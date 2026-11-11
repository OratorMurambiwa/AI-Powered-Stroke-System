"""Single-threaded credential-free model supervisor; fresh process per scan."""
import base64
import hashlib
import json
import os
import resource
import selectors
import signal
import sys
import time
import contextlib


def main():
    from .model import load, predict
    # Only the pinned trusted artifact is loaded. No request/input is read yet.
    with open(os.devnull,'w') as sink, contextlib.redirect_stdout(sink):
        model=load(threads=1)
    print('{"ready":true}',flush=True)
    for line in sys.stdin:
        if len(line)>1400000: raise ValueError('job_too_large')
        command=json.loads(line)
        limit=command.pop('_deadline',20)
        if type(limit) not in {int,float} or not 0<limit<=20: raise ValueError('invalid_deadline')
        read_fd,write_fd=os.pipe()
        pid=os.fork()
        if pid==0:
            os.close(read_fd)
            resource.setrlimit(resource.RLIMIT_CPU,(12,12))
            resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
            try:
                started=time.monotonic()
                raw=base64.b64decode(command['contentBase64'],validate=True)
                if hashlib.sha256(raw).hexdigest()!=command['scanSha256']: raise ValueError()
                with open(os.devnull,'w') as sink, contextlib.redirect_stdout(sink):
                    import torch
                    torch.set_num_threads(2)
                    result=predict(raw,model=model)
                result.update(scanSha256=command['scanSha256'],durationMs=round((time.monotonic()-started)*1000,3))
                output=json.dumps(result,allow_nan=False,separators=(',',':')).encode()
                if not 1<=len(output)<=4096: raise ValueError()
                os.write(write_fd,output)
                os.close(write_fd);os._exit(0)
            except BaseException:
                os._exit(1)
        os.close(write_fd)
        print(json.dumps({'started':pid}),flush=True)
        output=bytearray();deadline=time.monotonic()+limit;timed_out=False
        with selectors.DefaultSelector() as selector:
            selector.register(read_fd,selectors.EVENT_READ)
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0:timed_out=True;break
                if not selector.select(remaining):timed_out=True;break
                block=os.read(read_fd,4097-len(output))
                if not block:break
                output.extend(block)
                if len(output)>4096:break
        os.close(read_fd)
        if timed_out or len(output)>4096:
            try:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass
        _,status=os.waitpid(pid,0)
        if timed_out:reply={'error':'inference_deadline'}
        elif os.waitstatus_to_exitcode(status)!=0 or not output:reply={'error':'inference_failed'}
        else:reply={'result':json.loads(output)}
        print(json.dumps(reply,separators=(',',':')),flush=True)

if __name__=='__main__':
    try:main()
    except BaseException:raise SystemExit(1) from None

"""Credential-free controlled IPC workload and a stalled partial-line fault."""
import json,os,signal,subprocess,sys,time
from inference_worker.server import _line
from benchmarks.statistics import summary

def main():
    code="import sys; raw=b'{\"padding\":\"'+b'x'*1000+b'\"}\\n'; [sys.stdout.buffer.write(raw) or None for _ in range(200)]; sys.stdout.flush()"
    process=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,bufsize=0)
    samples=[];started=time.perf_counter()
    try:
        for _ in range(200):
            tick=time.perf_counter();assert len(_line(process,1)['padding'])==1000;samples.append((time.perf_counter()-tick)*1000)
        process.wait(timeout=2)
    finally:
        if process.poll() is None:process.kill();process.wait()
        process.stdout.close()
    elapsed=time.perf_counter()-started
    child_code="import sys,time;sys.stdout.write('READY\\n{');sys.stdout.flush();time.sleep(60)"
    probe="""import subprocess,sys,time,json
from inference_worker.server import _line
p=subprocess.Popen([sys.executable,'-c',CHILD],stdout=subprocess.PIPE,bufsize=0)
assert p.stdout.readline()==b'READY\\n'
t=time.monotonic()
try:
 try:_line(p,.05)
 except RuntimeError as e:print(json.dumps({'elapsedSeconds':time.monotonic()-t,'code':str(e)}))
finally:p.kill();p.wait()
""".replace('CHILD',repr(child_code))
    try:
        watchdog=subprocess.Popen([sys.executable,'-c',probe],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        output,error=watchdog.communicate(timeout=1)
        if watchdog.returncode:raise RuntimeError('probe failed')
        deadline={'bounded':True,**json.loads(output)}
        assert deadline['code']=='inference_deadline'
    except subprocess.TimeoutExpired:
        os.killpg(watchdog.pid,signal.SIGKILL);watchdog.communicate()
        deadline={'bounded':False,'watchdogSeconds':1}
    print(json.dumps({'schemaVersion':1,'lines':200,'bytesPerLine':1015,'elapsedSeconds':elapsed,
                      'lineRead':summary(samples),'partialLineDeadline':deadline},indent=2))
if __name__=='__main__':main()

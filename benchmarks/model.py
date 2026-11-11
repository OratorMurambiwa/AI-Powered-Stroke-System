"""Bounded networkless measurements of actual jobs; no medical evaluation data."""
import base64,hashlib,json,os,platform,threading,time
from pathlib import Path
from inference_worker.server import run_job
from inference_worker.probe import image
from benchmarks.statistics import summary

def memory():
    base=Path('/sys/fs/cgroup')
    # Linux cgroup v2 accounts shared pages once, unlike summed fork RSS.
    return {key:int((base/file).read_text()) for key,file in [('currentBytes','memory.current'),('peakBytes','memory.peak')]
            if (base/file).exists()}

def main():
    samples=[];outputs={};peaks=[];stop=threading.Event()
    def monitor():
        while not stop.wait(.01):
            value=memory()
            if value:peaks.append(value['currentBytes'])
    before=memory();thread=threading.Thread(target=monitor,daemon=True);thread.start()
    try:
        raw=image('black');job={'contentBase64':base64.b64encode(raw).decode(),'scanSha256':hashlib.sha256(raw).hexdigest()}
        start=time.perf_counter();run_job(job);startup=(time.perf_counter()-start)*1000
        # Explicit two warmups excluded; selftest and startup are reported separately.
        for _ in range(2):run_job(job)
        started=time.perf_counter()
        for index in range(30):
            pattern=('black','white','gradient')[index%3];raw=image(pattern)
            job={'contentBase64':base64.b64encode(raw).decode(),'scanSha256':hashlib.sha256(raw).hexdigest()}
            tick=time.perf_counter();result=run_job(job);elapsed=(time.perf_counter()-tick)*1000
            comparable={k:v for k,v in result.items() if k!='durationMs'}
            if pattern in outputs:assert outputs[pattern]==comparable,'nondeterministic output'
            outputs[pattern]=comparable
            samples.append({'pattern':pattern,'roundTripMs':elapsed,'workerJobMs':result['durationMs']})
        total=time.perf_counter()-started
    finally:stop.set();thread.join(timeout=1)
    print(json.dumps({'schemaVersion':1,'syntheticOnly':True,'python':platform.python_version(),
      'workload':'30 sequential jobs, 3 generated 64x64 patterns, 2 excluded warmups',
      'startupAndFirstJobMs':startup,'elapsedSeconds':total,'roundTrip':summary([s['roundTripMs'] for s in samples],total),
      'workerJob':summary([s['workerJobMs'] for s in samples]),'memoryBefore':before,'memoryAfter':memory(),
      'sampledPeakBytes':max(peaks) if peaks else None,'memorySampleIntervalMs':10,
      'samples':samples,'outputs':outputs},indent=2,allow_nan=False))

if __name__=='__main__':main()

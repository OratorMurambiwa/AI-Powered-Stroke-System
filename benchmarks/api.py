"""Bounded real gateway/API workload on the private disposable portal demo only."""
import base64,hashlib,json,os,platform,re,time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from uuid import uuid4
from benchmarks.statistics import summary
from benchmarks.synthetic import image

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def main():
    if os.environ.get('STROKE_SYNTHETIC_BENCHMARK')!='true':raise RuntimeError('explicit synthetic benchmark opt-in required')
    root=Path('/demo-private');run=json.loads((root/'run.json').read_text());fixture=json.loads((root/'credentials.json').read_text())
    if not re.fullmatch(r'stroke-portal-demo-[0-9]+-[0-9]+',run['project']):raise RuntimeError('owned fixture marker required')
    users=fixture['users'];tokens={};samples=defaultdict(list);status_counts=defaultdict(lambda:defaultdict(int));checks=[]
    opener=build_opener(ProxyHandler({}),NoRedirect())
    def call(method,path,role=None,body=None,expected=200,category=None):
        headers={'Content-Type':'application/json'}
        if role:headers['Authorization']='Bearer '+tokens[role]
        req=Request('http://127.0.0.1:4173'+path,method=method,headers=headers,data=json.dumps(body).encode() if body is not None else None)
        tick=time.perf_counter()
        try:response=opener.open(req,timeout=30)
        except HTTPError as error:response=error
        with response:
            status=response.status;raw=response.read(2000001)
            if len(raw)>2000000:raise AssertionError('oversized benchmark response')
            value=json.loads(raw) if raw and response.headers.get_content_type()=='application/json' else raw
        elapsed=(time.perf_counter()-tick)*1000
        if category:samples[category].append(elapsed);status_counts[category][str(status)]+=1
        if status!=expected:raise AssertionError(f'Unexpected status for bounded workload: {path.split("/")[-1]} {status} != {expected}')
        return value
    for role,user in users.items():
        if not user['email'].endswith('@example.test'):raise RuntimeError('synthetic accounts required')
        login=call('POST','/api/v1/identity/auth/login',body={k:user[k] for k in ['email','password']})
        tokens[role]=login['token']
    for _ in range(5):
        call('POST','/api/v1/identity/auth/login',body={k:users['patient'][k] for k in ['email','password']},category='login')
    for _ in range(20):
        call('GET','/api/v1/identity/me','doctor',category='live_identity')
        call('GET','/api/availability',category='public_availability')
    for i in range(5):
        slot=call('POST','/api/availability','doctor',{'date':f'2099-12-{i+1:02d}','startTime':'10:00','endTime':'11:00'},201,'publish_slot')
        appointment=call('POST','/api/v1/appointments','patient',{'schemaVersion':1,'availabilityId':slot['availability']['_id']},201,'book_appointment')
        if i<4:call('PATCH','/api/v1/appointments/'+appointment['appointmentId']+'/cancel','patient',{'schemaVersion':1},category='cancel_appointment')
    aid=appointment['appointmentId'];context=call('GET','/api/v1/clinical/appointment-context/'+aid,'doctor',category='appointment_context')
    command={k:context[k] for k in ['schemaVersion','sourceId','patientId','patientMappingId','clinicianMappingId']};command['requestId']=str(uuid4())
    receipt=call('POST',f'/api/v1/appointments/{aid}/assessment-requests','doctor',command,category='scheduled_encounter_intake')
    assert receipt['state']=='CREATED';encounter=receipt['encounterId'];base='/api/v1/clinical/encounters/'+encounter
    assert call('POST',f'/api/v1/appointments/{aid}/assessment-requests','doctor',command,category='scheduled_intake_replay')==receipt
    checks.append('same scheduled-intake command replays the exact encounter receipt')
    # Explicit assignment through the existing private fixture operator, never a public self-grant.
    control={'id':str(uuid4()),'action':'assign','encounterId':encounter};temp=root/'control-next.json';temp.write_text(json.dumps(control));temp.replace(root/'control.json')
    for _ in range(200):
        try:
            if json.loads((root/'control-ack.json').read_text())['id']==control['id']:break
        except FileNotFoundError:pass
        time.sleep(.05)
    else:raise AssertionError('private assignment deadline')
    for _ in range(20):call('GET',base+'/assessment','doctor',category='assigned_assessment_read')
    version=0
    def mutation(action,data,category=None,role='technician',expected=200,key=None):
        nonlocal version
        cmd={'schemaVersion':1,'requestId':key or str(uuid4()),'expectedVersion':version,'action':action,'data':data}
        result=call('POST',base+'/assessment',role,cmd,expected,category)
        if expected==200:version=result['version']
        return result
    from clinical_api.workflow import NIHSS_MAX
    mutation('OBSERVATIONS',{'vitals':{'systolicMmHg':120,'diastolicMmHg':80,'pulseBpm':70,'temperatureC':37,'oxygenPercent':98,'glucoseMgDl':90},
        'nihss':{k:0 for k in NIHSS_MAX},'observedAt':datetime.now(timezone.utc).isoformat()},'record_observations')
    mutation('SCAN',{'mediaType':'image/png','contentBase64':base64.b64encode(b'<svg onload="alert(1)"/>').decode()},expected=400)
    raw=image('gradient');scan=mutation('SCAN',{'mediaType':'image/png','contentBase64':base64.b64encode(raw).decode()},'upload_synthetic_png')['scanId']
    mutation('SUBMIT',{},'submit_assessment')
    for role in ['patient','otherPatient','technician','admin']:call('GET',base+'/predictions',role,expected=403)
    for path in [base+'/assessment',base+'/scans/'+scan]:call('GET',path,'otherPatient',expected=404)
    checks.append('wrong-patient scans/assessment 404; prediction roles 403; malicious PNG rejected')
    prediction_outputs=[];started=time.perf_counter()
    for _ in range(10):
        result=call('POST',base+'/predictions','doctor',{'schemaVersion':1,'requestId':str(uuid4()),'scanId':scan},category='clinical_real_inference')
        assert result['state']=='SUCCEEDED';prediction_outputs.append({k:result['prediction'][k] for k in ['modelSha256','scanSha256','predictedClass','scores']})
    inference_seconds=time.perf_counter()-started
    assert all(p==prediction_outputs[0] for p in prediction_outputs)
    duplicate={'schemaVersion':1,'requestId':str(uuid4()),'scanId':scan}
    def duplicate_call(_):
        # Own opener per thread: urllib handlers are not a shared connection pool.
        req=Request('http://127.0.0.1:4173'+base+'/predictions',data=json.dumps(duplicate).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+tokens['doctor']})
        with build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=30) as response:return response.status,json.loads(response.read(10000))
    with ThreadPoolExecutor(max_workers=3) as executor:results=list(executor.map(duplicate_call,range(3)))
    assert all(s in {200,202} for s,_ in results) and len({b['predictionId'] for _,b in results})==1
    replay=call('POST',base+'/predictions','doctor',duplicate);assert replay['attempts']==1
    checks.append('three concurrent identical inference commands share one prediction and one attempt')
    mutation('APPROVE',{'summary':'SYNTHETIC independently reviewed observations only; no AI diagnosis or treatment.','attested':True},'independent_approval',role='doctor')
    approved=call('GET',base+'/assessment','patient');assert 'history' not in approved and 'notes' not in approved['observations']
    for _ in range(20):
        assert call('GET',base+'/assessment','patient',category='patient_approved_result')==approved
        assert hashlib.sha256(call('GET',base+'/scans/'+scan,'patient',category='patient_private_scan')).hexdigest()==hashlib.sha256(raw).hexdigest()
    mutation('NOTE',{'text':'SYNTHETIC forbidden change'},role='doctor',expected=409)
    assert call('GET',base+'/assessment','patient')==approved
    checks.append('approved patient projection/scans isolated and immutable; model never added to findings')
    # Live session revocation through the actual authority, with no database mutation.
    call('POST','/api/v1/identity/auth/logout','doctor',{},expected=204)
    call('GET',base+'/assessment','doctor',expected=401);checks.append('revoked live doctor session denied')
    print(json.dumps({'schemaVersion':1,'syntheticOnly':True,'python':platform.python_version(),'workload':'sequential gateway HTTP; fresh disposable fixture; no retries in latency samples',
      'api':{k:{**summary(v), 'statusCounts':dict(status_counts[k]),'samplesMs':v} for k,v in samples.items()},
      'clinicalInferenceThroughputPerSecond':10/inference_seconds,'predictionParity':prediction_outputs[0],
      'securityReliabilityChecks':checks,'complete':True},indent=2,allow_nan=False))

if __name__=='__main__':main()

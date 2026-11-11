"""Fresh synthetic demo bootstrap with explicit fixture references, never real adoption."""
import json,os,sys,tempfile,threading
from pathlib import Path
from uuid import uuid4
from wsgiref.simple_server import make_server
from clinical_api.tests.fixtures import create_records
from clinical_api.config import Config
from clinical_api.linkage import LinkOperator
from clinical_api.app import ClinicalApplication
from clinical_api.__main__ import LocalClinicalServer,PrivateHandler
from clinical_api.validation import ISSUER

if os.environ.get('PORTAL_SYNTHETIC_DEMO')!='true': raise SystemExit('Synthetic demo opt-in required')
manifest=json.loads(sys.stdin.readline())
folder=Path(tempfile.mkdtemp(prefix='portal-synthetic-clinical-'))
source_id=str(uuid4());source=folder/'synthetic-source.sqlite';links=folder/'synthetic-links.sqlite'
create_records(source,source_id)
config=Config(source,links,source_id,manifest['authority'],4,os.environ['CLINICAL_INFERENCE_URL'],os.environ['INFERENCE_SERVICE_KEY'])
service=config.service();service.store.initialize();operator=LinkOperator(service.store,service.source,service.identity)
mappings={}
# Explicit approved fixture-reference map; no names/email/patient-code matching.
for key,role,native in [('patient','patient',1),('otherPatient','patient',2),('doctor','doctor',1),('technician','technician',2)]:
    person=operator.register_person({'schemaVersion':1,'sourceId':source_id,'role':role,'recordId':native},'synthetic-fixture-operator','SYNTHETIC independent record reference approval')
    actor=manifest['identities'][key]
    mappings[key]=operator.link({'schemaVersion':1,'issuer':ISSUER,'subject':actor['subject'],'role':role,'personId':person['personId']},actor['bearer'],'synthetic-fixture-operator','SYNTHETIC explicit subject/record proof')

manifest.clear();actor=None

def start():
    server=make_server('127.0.0.1',8010,ClinicalApplication(service),handler_class=PrivateHandler,server_class=LocalClinicalServer)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();return server,thread
server,thread=start()
print(json.dumps({'ready':True}),flush=True)
for line in sys.stdin:
    command=json.loads(line)
    try:
        action=command['action'];result={}
        if action=='assign':
            result=operator.assign({'schemaVersion':1,'mappingId':mappings['technician']['mappingId'],'encounterId':command['encounterId']},command['bearer'],'synthetic-fixture-operator','SYNTHETIC explicit technician assignment')
        elif action=='pauseClinical': server.shutdown();thread.join(timeout=3);server.server_close()
        elif action=='resumeClinical': server,thread=start()
        else: raise ValueError()
        print(json.dumps({'id':command['id'],'ok':True,'result':result}),flush=True)
    except Exception:
        print(json.dumps({'id':command.get('id'),'ok':False,'error':'operator_action_failed'}),flush=True)

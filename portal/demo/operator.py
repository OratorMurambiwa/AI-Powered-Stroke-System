"""Local synthetic operator handoff; never an HTTP route or public credential API."""
import json,os,sys,time,uuid
from pathlib import Path
if not sys.stdin.isatty(): raise SystemExit('Use a private interactive operator terminal; handoff is refused from redirected stdin.')
root=Path(sys.argv[1]);delivery=str(uuid.UUID(sys.argv[2]))
operator=input('Operator reference: ').strip()
if not operator or len(operator)>120:raise SystemExit('Bounded operator reference required')
if input('Registered recipient/channel independently verified? Type HANDOFF: ')!='HANDOFF':raise SystemExit('Handoff not authorized')
if (root/'delivery-once.json').exists():raise SystemExit('A previous private handoff file requires operator review')
command={'id':str(uuid.uuid4()),'action':'deliver','deliveryId':delivery,'verified':'HANDOFF','operator':operator}
path=root/'control-next.json'
with path.open('x') as stream:json.dump(command,stream)
os.chmod(path,0o600);path.replace(root/'control.json')
for _ in range(200):
    try:
        if json.loads((root/'control-ack.json').read_text())['id']==command['id']:
            payload=json.loads((root/'delivery-once.json').read_text());(root/'delivery-once.json').unlink()
            print('Sensitive single-use handoff — do not log, commit or paste into chat.',file=sys.stderr)
            print(json.dumps(payload));break
    except FileNotFoundError:pass
    time.sleep(.1)
else:raise SystemExit('Handoff not acknowledged; inspect private operator state before retrying')

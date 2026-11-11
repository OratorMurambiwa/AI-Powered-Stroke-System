#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .portal-demo/security
chmod 700 .portal-demo/security
python3 - <<'PYAUDIT'
from pathlib import Path
p=Path('inference_worker/requirements.lock').read_text()
Path('.portal-demo/security/upstream-lookup.txt').write_text(p.replace('torch==2.10.0+cpu','torch==2.10.0').replace('torchvision==0.25.0+cpu','torchvision==0.25.0'))
PYAUDIT
# Scanner lives in a throwaway target directory, never application requirements.
docker run --rm --memory 512m --cpus 1 --user "$(id -u):$(id -g)" -e XDG_CACHE_HOME=/tmp/audit-cache \
  -v "$PWD/inference_worker/requirements.lock:/audit/requirements.lock:ro" -v "$PWD/.portal-demo/security:/report" \
  --entrypoint sh stroke-inference:milestone4b -ec '
    python -m pip install --target /tmp/audit-tool pip-audit==2.9.0 > /tmp/audit-install.log 2>&1
    set +e
    PYTHONPATH=/tmp/audit-tool python -m pip_audit --disable-pip --no-deps -r /audit/requirements.lock --format json --output /report/python-audit-final.json
    audit_status=$?
    set -e
    test "$audit_status" -le 1
    # Separate metadata lookup projection; never use this as an installation lock.
    set +e
    PYTHONPATH=/tmp/audit-tool python -m pip_audit --disable-pip --no-deps -r /report/upstream-lookup.txt --format json --output /report/python-audit-upstream.json
    audit_status=$?
    set -e
    test "$audit_status" -le 1
  '
python3 - <<'PY'
import json
from datetime import datetime,timezone
from pathlib import Path
result={'schemaVersion':1,'scanner':'pip-audit 2.9.0','checkedAt':datetime.now(timezone.utc).isoformat(),
'cpuLookupNote':'Original +cpu distributions may be skipped by PyPI. Separate upstream lookup strips only the local +cpu suffix for matching upstream version advisories; it does not audit CPU wheel binaries or change the installation lock.','audits':{}}
for name,file in [('installed-lock','python-audit-final.json'),('upstream-version-lookup','python-audit-upstream.json')]:
 raw=json.loads((Path('.portal-demo/security')/file).read_text());deps=raw['dependencies']
 result['audits'][name]={'dependencies':len(deps),'advisoryRecords':sum(len(d.get('vulns',[])) for d in deps),
 'packages':[{'name':d['name'],'version':d.get('version'),'skipReason':d.get('skip_reason'),
 'advisories':[{'id':v['id'],'aliases':v.get('aliases',[]),'fixVersions':v.get('fix_versions',[])} for v in d.get('vulns',[])]} for d in deps]}
Path('docs/performance/dependency-audit.json').write_text(json.dumps(result,indent=2)+'\n')
print('Sanitized dependency audit saved; review advisoryRecords and skipReason before claiming coverage.')
PY

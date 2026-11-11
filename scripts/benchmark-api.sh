#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
label=${1:?Usage: benchmark-api.sh RUN_LABEL (fresh portal-demo start required)}
[[ "$label" =~ ^[a-z0-9-]{1,48}$ ]] || exit 1
out="$PWD/docs/performance/runs/$label"
[[ ! -e "$out" ]] || { echo 'Refusing to overwrite evidence'; exit 1; }
project=$(python3 - <<'PY'
import json,re
v=json.load(open('.portal-demo/run.json'));assert re.fullmatch(r'stroke-portal-demo-[0-9]+-[0-9]+',v['project']);print(v['project'])
PY
)
[[ "$(docker inspect -f '{{index .Config.Labels "org.medstroke.demo"}}' "$project-app")" == "$project" ]] || { echo 'Owned synthetic fixture required'; exit 1; }
mkdir -p "$out"
# This client has no worker admission key and no original database/scan/model mount.
docker run --rm --network "container:$project-app" --read-only --tmpfs /tmp:rw,size=64m --memory 256m --cpus 1 --pids-limit 32 --cap-drop ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" -e STROKE_SYNTHETIC_BENCHMARK=true \
  -v "$PWD/benchmarks:/repo/benchmarks:ro" -v "$PWD/clinical_api:/repo/clinical_api:ro" -v "$PWD/.portal-demo:/demo-private" -w /repo \
  stroke-portal-app:5b python -m benchmarks.api > "$out/api.json"
python3 - "$out" "$project" <<'PY'
import hashlib,json,subprocess,sys
from pathlib import Path
out=Path(sys.argv[1]);project=sys.argv[2]
result={'schemaVersion':1,'sourceCommit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
'harnessSha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('benchmarks').glob('*.py')},
'containers':{},'complete':True}
for suffix in ['app','mongo','inference']:
 # No docker inspect configuration/environment dump: fixed nonsecret fields only.
 fmt='{"imageId":{{json .Image}},"memoryLimit":{{.HostConfig.Memory}},"nanoCpus":{{.HostConfig.NanoCpus}}}'
 result['containers'][suffix]=json.loads(subprocess.check_output(['docker','inspect','--format',fmt,project+'-'+suffix],text=True))
(out/'conditions.json').write_text(json.dumps(result,indent=2)+'\n')
PY
echo "Completed synthetic API measurements: $out; stop this demo and start fresh before browser tests."

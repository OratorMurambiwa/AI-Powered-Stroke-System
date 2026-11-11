#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
image=${1:?Usage: benchmark-model.sh stroke-inference:TAG RUN_LABEL}
label=${2:?Run label required}
[[ "$image" =~ ^stroke-inference:[a-zA-Z0-9._-]+$ && "$label" =~ ^[a-z0-9-]{1,48}$ ]] || { echo 'Invalid local image or run label'; exit 1; }
out="$PWD/docs/performance/runs/$label"
[[ ! -e "$out" ]] || { echo 'Refusing to overwrite evidence'; exit 1; }
mkdir -p "$out"
# No service credentials, network, database/scan mounts or patient inputs.
args=(--rm --network none --read-only --tmpfs /tmp:rw,size=64m --cap-drop ALL --security-opt no-new-privileges --memory 1500m --cpus 2 --pids-limit 64 -v "$PWD/ml/MedStroke.pt:/artifact/MedStroke.pt:ro" -v "$PWD/benchmarks:/app/benchmarks:ro" --entrypoint python)
docker run "${args[@]}" "$image" -m benchmarks.model > "$out/model.json"
docker run "${args[@]}" "$image" -m benchmarks.ipc > "$out/ipc.json"
python3 - "$out" "$image" <<'PY'
import hashlib,json,platform,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
out=Path(sys.argv[1]);image=sys.argv[2]
def docker(*args):return subprocess.check_output(['docker',*args],text=True).strip()
files=['inference_worker/server.py','inference_worker/pool.py','inference_worker/model.py','benchmarks/model.py','benchmarks/ipc.py']
# Runtime source hashes come from the image, not the potentially different worktree.
runtime=json.loads(docker('run','--rm','--network','none','--entrypoint','python',image,'-c',"import hashlib,json;from pathlib import Path;print(json.dumps({p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['inference_worker/server.py','inference_worker/pool.py','inference_worker/model.py']}))"))
metadata={'schemaVersion':1,'sourceCommit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
'imageId':docker('image','inspect','--format','{{.Id}}',image),'runtimeSourceSha256':runtime,
'harnessSha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files if p.startswith('benchmarks/')},
'docker':json.loads(docker('info','--format','{{json .}}'))}
# Deliberately allowlist host metadata; never save a resolved environment/config.
info=metadata.pop('docker');metadata['hardware']={k:info[k] for k in ['NCPU','MemTotal','KernelVersion','OSType','Architecture','ServerVersion']}
metadata['hardware']['cpuModel']=next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),'unknown')
metadata['limits']={'cpus':2,'memoryBytes':1500*1024*1024,'pids':64,'tmpfsBytes':64*1024*1024,'network':'none','torchThreads':2}
metadata['runtimeVersions']=json.loads(docker('run','--rm','--network','none','--entrypoint','python',image,'-c',"import json,platform,importlib.metadata as m;print(json.dumps({'python':platform.python_version(),'pillow':m.version('pillow'),'torch':m.version('torch'),'torchvision':m.version('torchvision')}))"))
metadata['completedAtUtc']=datetime.now(timezone.utc).isoformat()
metadata['complete']=True
(out/'conditions.json').write_text(json.dumps(metadata,indent=2)+'\n')
PY
echo "Completed sanitized synthetic measurements: $out"

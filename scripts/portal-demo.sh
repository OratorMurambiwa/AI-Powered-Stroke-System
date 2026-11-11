#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
state="$PWD/.portal-demo"
action=${1:-start}
read_run() { python3 - "$state/run.json" <<'PY'
import json,re,sys
v=json.load(open(sys.argv[1])); p=v['project']; assert re.fullmatch(r'stroke-portal-demo-[0-9]+-[0-9]+',p); print(p)
PY
}
stop_owned() {
  local project=$1
  for suffix in app mongo inference; do
    if [[ "$(docker inspect -f '{{index .Config.Labels "org.medstroke.demo"}}' "$project-$suffix" 2>/dev/null || true)" == "$project" ]]; then docker rm -f "$project-$suffix" >/dev/null; fi
  done
  if [[ "$(docker network inspect -f '{{index .Labels "org.medstroke.demo"}}' "$project" 2>/dev/null || true)" == "$project" ]]; then docker network rm "$project" >/dev/null; fi
  if [[ "$(docker network inspect -f '{{index .Labels "org.medstroke.demo"}}' "$project-inference" 2>/dev/null || true)" == "$project" ]]; then docker network rm "$project-inference" >/dev/null; fi
  rm -f "$state/worker.env" "$state/delivery-once.json" "$state/credentials.json" "$state/control.json" "$state/control-ack.json"
}
case "$action" in
start)
  command -v flock >/dev/null
  exec 9>"$(git rev-parse --git-path stroke-backend-tests.lock)"
  flock -n 9 || { echo 'Another backend build/test runner is active'; exit 1; }
  [[ ! -e "$state/run.json" ]] || { echo 'Demo state already exists; run scripts/portal-demo.sh stop first'; exit 1; }
  mkdir -p "$state"; chmod 700 "$state"
  port=${PORTAL_PORT:-4180}
  [[ "$port" =~ ^[0-9]{4,5}$ ]] && ((port>=1024&&port<=65535)) || { echo 'Invalid loopback demo port'; exit 1; }
  project="stroke-portal-demo-$(date +%s)-$$"
  python3 - "$state/run.json" "$project" "$port" <<'PY'
import json,os,sys
with open(sys.argv[1],'x') as f: json.dump({'project':sys.argv[2],'port':int(sys.argv[3])},f)
os.chmod(sys.argv[1],0o600)
PY
  successful=false
  cleanup_start() { if [[ "$successful" != true ]]; then stop_owned "$project"; mv "$state/run.json" "$state/last-run.json"; fi; }
  trap cleanup_start EXIT
  mkdir -p "$state/npm-cache"
  docker run --rm -v "$state/npm-cache:/root/.npm" -v "$PWD/booking-backend:/repo/booking-backend" -v "$PWD/portal:/repo/portal" -w /repo node:22.14.0-alpine sh -ec 'cd booking-backend; npm ci --prefer-offline --fetch-retries=2 --fetch-timeout=60000; npm run build; cd ../portal; npm ci --prefer-offline --fetch-retries=2 --fetch-timeout=60000; npm test; npm run build; npm audit'
  docker network create --label "org.medstroke.demo=$project" "$project" >/dev/null
  docker run -d --name "$project-mongo" --label "org.medstroke.demo=$project" --network "$project" --network-alias stroke-portal-mongo \
    --memory 512m --cpus 1 --tmpfs /data/db --tmpfs /data/configdb \
    'mongo:8.0.17@sha256:9814652e33f0cf8b9fddea8b46dfc9d8e19b130dcfdd7b510ca58bb0d40c8b71' --replSet rs0 --bind_ip_all >/dev/null
  ready=false
  for _ in {1..40}; do
    if docker exec "$project-mongo" mongosh --quiet --eval 'quit(db.adminCommand({ping:1}).ok?0:1)' >/dev/null 2>&1; then ready=true; break; fi
    sleep 1
  done
  [[ "$ready" == true ]] || { echo 'Synthetic MongoDB failed readiness'; exit 1; }
  docker exec "$project-mongo" mongosh --quiet --eval 'rs.initiate({_id:"rs0",members:[{_id:0,host:"stroke-portal-mongo:27017"}]})' >/dev/null
  ready=false
  for _ in {1..40}; do
    if docker exec "$project-mongo" mongosh --quiet --eval 'quit(db.hello().isWritablePrimary?0:1)' >/dev/null 2>&1; then ready=true; break; fi
    sleep 1
  done
  [[ "$ready" == true ]] || { echo 'Synthetic MongoDB did not elect primary'; exit 1; }
  docker build -t stroke-portal-app:5b -f portal/demo/Dockerfile portal/demo
  docker image inspect stroke-inference:milestone4b >/dev/null
  python3 - "$state/worker.env" <<'PYKEY'
import secrets,sys,os
with open(sys.argv[1],'x') as f:f.write('INFERENCE_SERVICE_KEY='+secrets.token_hex(32)+'\n')
os.chmod(sys.argv[1],0o600)
PYKEY
  docker network create --internal --label "org.medstroke.demo=$project" "$project-inference" >/dev/null
  docker run -d --name "$project-inference" --label "org.medstroke.demo=$project" --network "$project-inference" --network-alias stroke-inference-worker \
    --env-file "$state/worker.env" --read-only --tmpfs /tmp:rw,size=64m --memory 1500m --cpus 2 --pids-limit 64 --cap-drop ALL --security-opt no-new-privileges \
    -v "$PWD/ml/MedStroke.pt:/artifact/MedStroke.pt:ro" stroke-inference:milestone4b >/dev/null
  ready=false
  for _ in {1..80}; do
    if docker exec "$project-inference" python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8020/health",timeout=1).read()' >/dev/null 2>&1; then ready=true; break; fi
    sleep 1
  done
  [[ "$ready" == true ]] || { echo 'Inference worker readiness failed'; exit 1; }
  docker run -d --name "$project-app" --label "org.medstroke.demo=$project" --network "$project" --network "$project-inference" --network-alias stroke-portal-app --env-file "$state/worker.env" \
    --user "$(id -u):$(id -g)" --read-only --tmpfs /tmp --memory 512m --cpus 1 --cap-drop ALL --security-opt no-new-privileges \
    -p "127.0.0.1:$port:4173" \
    -v "$PWD/booking-backend/dist:/repo/booking-backend/dist:ro" -v "$PWD/booking-backend/node_modules:/repo/booking-backend/node_modules:ro" \
    -v "$PWD/portal/dist:/repo/portal/dist:ro" -v "$PWD/portal/demo/server.cjs:/repo/portal/demo/server.cjs:ro" -v "$PWD/portal/demo/clinical.py:/repo/portal/demo/clinical.py:ro" -v "$PWD/clinical_api:/repo/clinical_api:ro" \
    -v "$state:/demo-private" -w /repo \
    -e MONGODB_URI='mongodb://stroke-portal-mongo:27017/synthetic_portal_demo?replicaSet=rs0' -e PORTAL_SYNTHETIC_DEMO=true \
    stroke-portal-app:5b node portal/demo/server.cjs >/dev/null
  ready=false
  for _ in {1..40}; do
    if [[ -f "$state/credentials.json" ]] && docker exec "$project-app" node -e 'fetch("http://127.0.0.1:4173/api/health").then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))' >/dev/null 2>&1; then ready=true; break; fi
    sleep 1
  done
  [[ "$ready" == true ]] || { echo 'Synthetic demo API failed readiness'; exit 1; }
  successful=true
  echo "Synthetic portal ready: http://127.0.0.1:$port"
  echo "Private, newly generated synthetic accounts: $state/credentials.json (mode 0600). Do not publish this file."
  ;;
stop)
  [[ -f "$state/run.json" ]] || { echo 'No owned demo is recorded'; exit 0; }
  project=$(read_run); stop_owned "$project"; mv "$state/run.json" "$state/last-run.json"; echo 'Owned synthetic demo stopped. No persistent volumes were deleted.'
  ;;
test)
  project=$(read_run)
  docker image inspect stroke-portal-browser:5a >/dev/null
  docker run --rm --network "container:$project-app" --memory 1200m --cpus 2 --shm-size 256m \
    -e PORTAL_TEST_URL=http://127.0.0.1:4173 -v "$PWD/portal/tests:/tests:ro" -v "$state:/demo-private" \
    --entrypoint python stroke-portal-browser:5a /tests/browser.py
  docker run --rm --network "container:$project-app" --memory 1200m --cpus 2 --shm-size 256m \
    -e PORTAL_TEST_URL=http://127.0.0.1:4173 -v "$PWD/portal/tests:/tests:ro" -v "$state:/demo-private" \
    --entrypoint python stroke-portal-browser:5a /tests/browser_clinical.py
  ;;
deliver)
  project=$(read_run)
  python3 portal/demo/operator.py "$state" "${2:-}"
  ;;
assign)
  project=$(read_run)
  python3 - "$state" "${2:-}" <<'PYASSIGN'
import json,sys,time,uuid
from pathlib import Path
root=Path(sys.argv[1]);encounter=str(uuid.UUID(sys.argv[2]));command={'id':str(uuid.uuid4()),'action':'assign','encounterId':encounter}
tmp=root/'control-next.json';tmp.write_text(json.dumps(command));tmp.replace(root/'control.json')
for _ in range(200):
 try:
  if json.loads((root/'control-ack.json').read_text())['id']==command['id']:print('Explicit synthetic technician assignment recorded');break
 except FileNotFoundError:pass
 time.sleep(.1)
else:raise SystemExit('Operator assignment not acknowledged')
PYASSIGN
  ;;
*) echo 'Usage: scripts/portal-demo.sh start|test|stop|assign ENCOUNTER_UUID|deliver DELIVERY_UUID'; exit 1;;
esac

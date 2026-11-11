#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Both runners share node_modules/dist; never allow overlapping dependency builds.
command -v flock >/dev/null || { echo 'flock is required for isolated test serialization' >&2; exit 1; }
exec 9>"$(git rev-parse --git-path stroke-backend-tests.lock)"
flock -n 9 || { echo 'Another backend/clinical test runner is active; retry after it finishes' >&2; exit 1; }
project="stroke-clinical-test-$(date +%s)-$$"
mongo_image='mongo:8.0.17@sha256:9814652e33f0cf8b9fddea8b46dfc9d8e19b130dcfdd7b510ca58bb0d40c8b71'
private_env=$(mktemp /tmp/stroke-inference-env.XXXXXX)
chmod 600 "$private_env"
python3 - "$private_env" <<'PYKEY'
import secrets,sys
from pathlib import Path
Path(sys.argv[1]).write_text('INFERENCE_SERVICE_KEY='+secrets.token_hex(32)+'\n')
PYKEY
cleanup() {
  docker rm -f "$project-mongo" >/dev/null 2>&1 || true
  docker rm -f "$project-inference" >/dev/null 2>&1 || true
  docker network rm "$project-inference" >/dev/null 2>&1 || true
  rm -f "$private_env"
  docker network rm "$project" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
# Dedicated network and tmpfs database only; no ports or persistent data mounts.
docker network create "$project" >/dev/null
docker run -d --name "$project-mongo" --network "$project" \
  --network-alias stroke-booking-mongo --tmpfs /data/db --tmpfs /data/configdb \
  "$mongo_image" --replSet rs0 --bind_ip_all >/dev/null
ready=false
for _ in {1..40}; do
  if docker exec "$project-mongo" mongosh --quiet --eval 'quit(db.adminCommand({ping:1}).ok ? 0 : 1)' >/dev/null 2>&1; then
    ready=true; break
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then echo 'Synthetic MongoDB failed to start' >&2; exit 1; fi
docker exec "$project-mongo" mongosh --quiet --eval \
  'rs.initiate({_id:"rs0",members:[{_id:0,host:"stroke-booking-mongo:27017"}]})' >/dev/null
ready=false
for _ in {1..40}; do
  if docker exec "$project-mongo" mongosh --quiet --eval 'quit(db.hello().isWritablePrimary ? 0 : 1)' >/dev/null 2>&1; then
    ready=true; break
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then echo 'Synthetic MongoDB failed to elect a primary' >&2; exit 1; fi
# Build explicitly before this helper: weights are never copied into the image.
docker image inspect stroke-inference:milestone4b >/dev/null
docker network create --internal "$project-inference" >/dev/null
docker run -d --name "$project-inference" --network "$project-inference" \
  --network-alias stroke-inference-worker --env-file "$private_env" \
  --read-only --tmpfs /tmp:rw,size=64m --memory 1500m --cpus 2 --pids-limit 64 \
  --cap-drop ALL --security-opt no-new-privileges \
  -v "$PWD/ml/MedStroke.pt:/artifact/MedStroke.pt:ro" stroke-inference:milestone4b >/dev/null
ready=false
for _ in {1..80}; do
  if docker exec "$project-inference" python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8020/health", timeout=1).read()' >/dev/null 2>&1; then
    ready=true; break
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then echo 'Restricted inference worker failed its real CPU startup gate' >&2; docker inspect --format 'Worker status={{.State.Status}} exit={{.State.ExitCode}} OOM={{.State.OOMKilled}}' "$project-inference" >&2; docker logs --tail=5 "$project-inference" >&2; exit 1; fi
# Standalone worker tests run with no network, using the real read-only artifact.
docker run --rm --network none --read-only --tmpfs /tmp:rw,size=64m \
  --memory 1500m --cpus 2 --pids-limit 64 --cap-drop ALL --security-opt no-new-privileges \
  -v "$PWD/ml/MedStroke.pt:/artifact/MedStroke.pt:ro" --entrypoint python stroke-inference:milestone4b \
  -m unittest discover -s inference_worker/tests -v
docker run --rm --network "$project" --network "$project-inference" --env-file "$private_env" \
  -e TEST_INFERENCE_URL=http://stroke-inference-worker:8020/api/v1/predict -v "$PWD:/repo" -w /repo --tmpfs /tmp \
  -e PYTHONPYCACHEPREFIX=/tmp/stroke-python-cache \
  -e TEST_MONGODB_URI='mongodb://stroke-booking-mongo:27017/synthetic_booking_test?replicaSet=rs0' \
  node:22.14.0-alpine sh -ec '
    apk add --no-cache python3
    cd /repo/booking-backend
    npm ci
    npm test
    npm audit
    cd /repo
    python3 -m unittest discover -s clinical_api/tests -v
    python3 -m unittest discover -s tests -v
    python3 -m compileall -q clinical_api app.py core models pages services
  '

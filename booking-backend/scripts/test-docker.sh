#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
project="stroke-booking-test-$(date +%s)-$$"
mongo_image='mongo:8.0.17@sha256:9814652e33f0cf8b9fddea8b46dfc9d8e19b130dcfdd7b510ca58bb0d40c8b71'
cleanup() {
  docker rm -f "$project-mongo" >/dev/null 2>&1 || true
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
docker run --rm --network "$project" -v "$PWD:/work" -w /work \
  -e TEST_MONGODB_URI='mongodb://stroke-booking-mongo:27017/synthetic_booking_test?replicaSet=rs0' \
  node:22.14.0-alpine sh -c 'npm ci && npm test && npm audit'

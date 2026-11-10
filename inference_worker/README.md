# Private experimental CPU worker

Read [artifact trust/audit and actual outputs](../docs/experimental-models/medstroke-audit.md) and [API/isolation contract](../docs/experimental-predictions-v1.md). Only the explicitly confirmed fingerprint is accepted. Never substitute another checkpoint or enable unrestricted deserialization.

Build and test from the repository root:

```sh
docker build -f inference_worker/Dockerfile -t stroke-inference:milestone4b .
bash scripts/test-clinical-bridge.sh
```

The test helper generates a temporary private random admission key, starts only an internal-network inference container and isolated tmpfs MongoDB, and runs all prior/new tests. No host API port or normal database is used. It needs host Git, flock, Python 3 and Docker; legacy inference dependencies are not installed on the host.

Runtime entrypoint is `python -m inference_worker.server`. An explicitly supplied `INFERENCE_SERVICE_KEY` must be 64 lowercase hex characters generated with a secure random source, kept in an ignored operator-owned environment file (mode 0600). There is no default/test runtime credential. Mount the existing approved model file read-only at `/artifact/MedStroke.pt`. Use the read-only/nonroot/network/resource restrictions demonstrated in the helper. Connect only the authorized clinical caller to that internal network; do not publish worker port 8020 to a public interface.

Clinical API enablement requires a separately initialized fresh synthetic v4 store, matching explicit key and canonical private `CLINICAL_INFERENCE_URL`. The worker receives no identity JWT or DB path. Starting it performs an actual bounded CPU smoke job; failure prevents HTTP readiness. A non-busy job always launches a new bounded child, never an unbounded background queue or hosted fallback.

A networkless manual synthetic probe can be run with the same limits (only after approving the exact artifact):

```sh
docker run --rm --network none --read-only --tmpfs /tmp:rw,size=64m \
  --cap-drop ALL --security-opt no-new-privileges --memory 1500m --cpus 2 --pids-limit 64 \
  -v "$PWD/ml/MedStroke.pt:/artifact/MedStroke.pt:ro" \
  --entrypoint python stroke-inference:milestone4b -m inference_worker.probe
```

The output is uncalibrated model scores on nonmedical synthetic patterns, not diagnoses or a clinical accuracy evaluation. Every result remains experimental and subject to independent clinician review; review never approves a diagnosis or exposes these records to patients.

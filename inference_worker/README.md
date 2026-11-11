# Private experimental CPU worker

Read [artifact trust/audit and actual outputs](../docs/experimental-models/medstroke-audit.md) and [API/isolation contract](../docs/experimental-predictions-v1.md). Only the explicitly confirmed fingerprint is accepted. Never substitute another checkpoint or enable unrestricted deserialization.

Build and test from the repository root:

```sh
docker build -f inference_worker/Dockerfile -t stroke-inference:milestone4b .
bash scripts/test-clinical-bridge.sh
```

The test helper generates a temporary private random admission key, starts only an internal-network inference container and isolated tmpfs MongoDB, and runs all prior/new tests. No host API port or normal database is used. It needs host Git, flock, Python 3 and Docker; legacy inference dependencies are not installed on the host.

Runtime entrypoint is `python -m inference_worker.server`. An explicitly supplied `INFERENCE_SERVICE_KEY` must be 64 lowercase hex characters generated with a secure random source, kept in an ignored operator-owned environment file (mode 0600). There is no default/test runtime credential. Mount the existing approved model file read-only at `/artifact/MedStroke.pt`. Use the read-only/nonroot/network/resource restrictions demonstrated in the helper. Connect only the authorized clinical caller to that internal network; do not publish worker port 8020 to a public interface.

Clinical API enablement requires a separately initialized fresh synthetic v4 store, matching explicit key and canonical private `CLINICAL_INFERENCE_URL`. The worker receives no identity JWT or DB path. Starting it performs an actual bounded CPU smoke job; failure prevents HTTP readiness. A credential-free single-threaded supervisor loads the hash-pinned trusted artifact once within a separate 60-second startup bound, with Ultralytics offline mode and auto-install disabled. Each admitted scan forks a fresh child with 12 CPU seconds and 20 seconds wall time; no background queue or hosted fallback exists. The supervisor reaps timed-out children; IPC failure closes the supervisor process group and fails closed. The HTTP parent retains the admission key, which is excluded from the supervisor/child environment. Model digest is rechecked per job. Reported durationMs measures the scan job, excluding startup.

A networkless manual synthetic probe can be run with the same limits (only after approving the exact artifact):

```sh
docker run --rm --network none --read-only --tmpfs /tmp:rw,size=64m \
  --cap-drop ALL --security-opt no-new-privileges --memory 1500m --cpus 2 --pids-limit 64 \
  -v "$PWD/ml/MedStroke.pt:/artifact/MedStroke.pt:ro" \
  --entrypoint python stroke-inference:milestone4b -m inference_worker.probe
```

The output is uncalibrated model scores on nonmedical synthetic patterns, not diagnoses or a clinical accuracy evaluation. Every result remains experimental and subject to independent clinician review; review never approves a diagnosis or exposes these records to patients.

Milestone 6 bounds the complete supervisor reply read, including partial lines, and checks live supervisor state in `/health` (503/ready:false after failure). Restart explicitly after supervisor failure; it must pass the real startup inference again. Fixed-limit baseline/candidate benchmarks and real worker fault tests are documented in [performance methodology](../docs/performance/README.md); transport savings are not a demonstrated neural-inference speedup.

The Milestone 6 security update pins Pillow 13.0.0 using an actual isolated `pip freeze` after `pip check`; all other worker dependencies and model weights are unchanged. Exact generated-image prediction parity and the full regression suite gate this decoder update; this does not establish medical accuracy. See the [dependency findings and limits](../docs/hospital-milestone-6-verification.md).

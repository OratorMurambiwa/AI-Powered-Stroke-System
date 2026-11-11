# Milestone 6 reproducible local validation

Only fresh synthetic fixtures are allowed. Never run these helpers against real patient services. The model runner mounts the exact previously trusted checkpoint read-only, no databases/scans, and has no network or credentials. The API runner requires a labeled disposable portal demo and communicates only through its loopback gateway; it receives generated demo credentials, never internal worker credentials. Outputs below contain public configuration, timings, synthetic score vectors and source hashes only.

## Model and transport measurements

```sh
# Preserve/build af6fbf7 in a separate code-only checkout for the baseline image.
# Existing 5B image can be preserved before rebuilding:
docker tag stroke-inference:milestone4b stroke-inference:milestone5b-baseline
# Build the current candidate from this checkout:
docker build -f inference_worker/Dockerfile -t stroke-inference:milestone4b .
bash scripts/benchmark-model.sh stroke-inference:milestone5b-baseline baseline-1
bash scripts/benchmark-model.sh stroke-inference:milestone4b final-security-1
bash scripts/benchmark-model.sh stroke-inference:milestone5b-baseline baseline-2
bash scripts/benchmark-model.sh stroke-inference:milestone4b final-security-2
```

If the default image already contains milestone 6, build baseline from commit `af6fbf7` instead of retagging it. Verify `conditions.json` runtime source hashes, not just mutable image tags. Helpers refuse to overwrite existing evidence; choose fresh labels for repeats. A run is complete only when `conditions.json` has `complete: true`. Incomplete directories are not successful evidence.

Each fresh container has 2 CPU quota, 1500 MiB memory, 64 PIDs, 64 MiB private tmpfs, read-only root/model, dropped capabilities/no-new-privileges and network none. Measure cold startup plus first real job separately; exclude two warmups. Execute 30 sequential fresh-child jobs cycling deterministic black/white/gradient 64×64 grayscale PNGs (10 each), always the same 224×224 model preprocessing. There is no medical ground truth. Preserve full vectors/input/model hashes and compare exact baseline/candidate equality, excluding durations. The first two candidates isolate the IPC fix with Pillow 11.3.0; `final-security-1`/`final-security-2` additionally include the Pillow 13.0.0 decoder patch. `benchmarks.parity` covers eight further grayscale/RGB inputs at varied shapes to gate that dependency change. To reproduce the historical IPC-only candidates, use current worker source with the unchanged baseline Pillow 11.3.0 lock in a separate code-only checkout; do not edit the working runtime lock or reuse the final-image label. Runtime source hashes are identical between IPC-only and final candidates; runtime package versions/image IDs distinguish the decoder patch. The paired runs alternate to expose host variability; there is no significance or clinical throughput claim.

`roundTripMs` measures supervisor IPC, fork, scan validation/hash check, decode/preprocessing, real forward pass, reply and reap. `workerJobMs` excludes parent IPC/fork/reap and cold import/model startup. Sequential throughput is completed jobs / actual measured loop wall time, with no think time, no queue and no concurrency. Quantiles use nearest rank `sorted[ceil(p*n)-1]`; p95 on 30 observations is the 29th ordered sample, not a stable tail estimate or SLO.

Memory is Linux **cgroup v2** `memory.current` / `memory.peak`, counting the container and shared fork pages once. A 10 ms sampler supplements the kernel peak; samples may miss brief peaks. It includes accounted cache/runtime pages, not summed process RSS or model file size. No long-running leak/soak claim is made. Hardware, Docker kernel/resources, image ID and runtime/harness source hashes are allowlisted in each conditions file. Host is shared WSL with no CPU pinning/frequency control; quotas are bounds, not dedicated physical cores.

The IPC microbenchmark reads 200 actual 1015-byte JSON lines from a credential-free Python subprocess. It separately sends a readable unterminated reply and imposes a 50 ms line deadline; an outer 1 s process-group watchdog records baseline deadline escape. This is a controlled transport workload, not neural inference, hospital throughput or a production attack endpoint. Initial exploratory host runs are excluded; committed pairs ran under the same Docker limits.

## Real API and reliability validation

```sh
bash scripts/portal-demo.sh start
bash scripts/benchmark-api.sh api-1
bash scripts/portal-demo.sh stop
# Fresh demo required before the existing browser suite:
bash scripts/portal-demo.sh start
bash scripts/portal-demo.sh test
bash scripts/portal-demo.sh stop
bash scripts/test-clinical-bridge.sh
python3 -m unittest discover -s benchmarks -v
python3 -m benchmarks.verify_results
python3 scripts/audit-model-provenance.py
bash scripts/audit-worker-dependencies.sh
```

The API workload uses a stdlib client (1 CPU / 256 MiB), same network namespace as the gateway, actual new HTTP connections and no connection-pool warmup. It includes gateway + real Express/Mongo or Python/SQLite + live authority checks and committed clinical audits. Requests are sequential; no latency sample silently retries. Five login samples, twenty reads/category, five slot publications/bookings, four cancellations, one scheduled intake/capture/review sequence and ten distinct real inference requests are fixed. Single-operation categories are point timings, not useful percentiles. Booking remains within its existing ten/minute limiter; the demo's pre-existing API-wide 10000 limit is recorded rather than marketed as production protection. It is not a capacity/load/Internet/TLS benchmark.

The same API run checks unauthorized roles, cross-patient scans/records, malicious PNG, three identical concurrent inference requests/replay, immutable approval and actual session logout/revocation. It retains no identities, tokens, uploaded bytes or clinical UUIDs in the result. Tests separately exercise actual worker busy admission (eight simultaneous real requests), invalid/truncated bodies, supervisor death/health/inference failure and restart recovery, partial/coalesced/oversized IPC, plus all previous real service outages, retries, assignment/role invalidation, audit failure and upload regression cases. Synthetic data alone is used; no real-patient migration or model evaluation data is downloaded.

## Model validation boundary

[Static notebook audit](provenance.json) records source-cell hashes without executing notebook cells or inspecting outputs. It identifies a training data lead, not a trusted checkpoint lineage or independent test cohort. See the [Milestone 6 report](../hospital-milestone-6-verification.md) for external dataset investigation, blockers and actual results. Accuracy, precision, recall, F1 and confusion matrix remain unmeasured until representative licensed ground truth, patient-grouped independent splits and checkpoint/data lineage are established. Never assign truth labels to these synthetic patterns.

Dependency auditing uses a pinned scanner installed into a disposable target directory. Raw public advisory responses stay ignored under `.portal-demo/security`; sanitized summaries are tracked. CPU `+cpu` versions may be absent from PyPI, so a separately labeled lookup strips only that local suffix; it is not an installation lock or CPU binary/OS vulnerability scan. Review skips and findings, not just exit status. Initial cache/UID tool setup failures are excluded from final audit evidence.

Historical `benchmarks/ipc_v1.py` exactly matches the source hash for the initial six runs. Its outer fault watchdog included interpreter startup; one final-security-1 probe is explicitly inconclusive. Current `benchmarks/ipc.py` sends a readiness handshake before starting that watchdog. V2 baseline/candidate results are stored separately in `ipc-v2/`; no original run is overwritten or hidden. Final model timings and parity remain valid, independent of that diagnostic observer.

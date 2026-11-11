# Milestone 6 — performance, reliability and security validation

Baseline: `af6fbf7ca5cf9fbfaefa0320d178f5a73a1ca20d`. Synthetic fixtures only; original databases, scans, model weights, credentials and legacy/root dependency locks remain unchanged. [Reproduction/methodology](performance/README.md), [raw measurements](performance/runs/) and [source audit](performance/provenance.json) contain the detailed evidence.

## Clinical evaluation remains blocked

Static notebook source inspection, without execution/output inspection, identified a potential training source: [Kaggle Brain Stroke CT Dataset](https://www.kaggle.com/datasets/ozguraslank/brain-stroke-ct-dataset). Code shuffles images into 70/15/15 splits with seed 42, without sorted enumeration or patient/study grouping; it trains YOLO classification for 20 epochs at 224px and calls `model.val()` without explicitly selecting test. There is no immutable dataset/split manifest or verified link from that run to this checkpoint. Stored notebook metrics/confusion-matrix output were not adopted.

Public metadata investigation found [PhysioNet CT-ICH](https://physionet.org/content/ct-ich/1.3.1/) (restricted hemorrhage resource) and [Stanford SinoCT](https://aimi.stanford.edu/datasets/sinoct) (normal/abnormal labels, partial RSNA challenge overlap). Neither establishes an independent bleeding/ischemia/normal cohort for this checkpoint. Kaggle metadata was not readable in the browser; filename/hash searches established no trusted release/model card. No clinical images were downloaded or original data inspected.

**Accuracy, precision, recall, F1 and confusion matrix: not measured.** Required: verified checkpoint/training lineage, licensed versioned ground truth, patient-grouped independent cohort, leakage/duplicate review, clinician-adjudicated labels, representative acquisition/subgroup coverage and approved preprocessing/windowing. Then evaluate per-class/macro/weighted metrics, support, confusion matrix and patient-level uncertainty intervals on a locked cohort. Synthetic patterns establish executable parity only; artifact trust is not clinical validation.

## CPU measurements and optimization

Shared Intel Core Ultra 5 225U / 14 logical CPUs, WSL2 6.6.87.2, Docker 29.9.2, 7.22 GiB RAM. Workers use Python 3.12.11, existing CPU torch/vision, 2 CPU quota, 1500 MiB, 64 PIDs, read-only root/model, no GPU/network. Each fresh container executes two excluded warmups and 30 sequential generated 64×64 PNG jobs. Quantiles use nearest rank; throughput uses actual loop wall time. Cold startup is recorded separately. Memory is cgroup v2 kernel peak, counting shared fork pages once, not summed RSS. Conditions include image/source hashes and hardware; host scheduling/frequency is uncontrolled.

| Run | Round-trip p50 / p95 (ms) | Jobs/s | Peak MiB |
| --- | --- | --- | --- |
| Baseline 1 | 165.37 / 394.23 | 4.90 | 258.04 |
| IPC candidate 1 | 177.93 / 308.07 | 5.05 | 263.73 |
| Baseline 2 | 156.08 / 238.62 | 5.80 | 262.21 |
| IPC candidate 2 | 187.65 / 353.52 | 4.72 | 260.07 |
| Final Pillow 13 run 1 | 174.47 / 293.17 | 5.02 | 260.16 |
| Final Pillow 13 run 2 | 209.31 / 360.11 | 4.19 | 259.79 |

**No dependable overall inference speedup is demonstrated.** Final worker-job p50 was 146.10/182.21 ms; median fork/IPC/reap overhead was 33.80/32.39 ms. Inner validation/hash/decode/preprocessing/forward stages were not individually profiled. Fresh-child isolation, threads, precision, preprocessing and weights were retained. All **180 measured jobs** have exact baseline/candidate labels, full score vectors and provenance equality; [eight additional grayscale/RGB shape inputs](performance/parity.json) also match exactly across Pillow 11.3/13.0. These samples do not establish capacity, clinical performance, stable tail latency or long-term leak freedom.

Confirmed fixes:

- **IPC deadline escape:** the old reader selected once then blocked on an incomplete line. Bounded chunk reads now apply a monotonic deadline to the complete message and preserve coalesced replies. In the [readiness-isolated v2 probe](performance/ipc-v2/), baseline required a 1-second watchdog; final code terminated at **50.71 ms** for a 50 ms deadline. Per-job 12 CPU/20 wall seconds and 60-second startup limits remain.
- **False healthy status:** killing the real owned model supervisor reproduced baseline `/health` 200. Health now returns **503/ready:false**; inference fails closed and explicit restart passes actual CPU readiness before recovery.

The controlled 200×1015-byte IPC workload improved p50/p95 from **2.172/5.933** and **1.025/2.502 ms** to **0.020/0.089** and **0.030/0.275 ms**. This is transport improvement, not model throughput improvement. One later v1 fault probe was inconclusive because its watchdog included interpreter startup; [original evidence and exact historical harness](performance/probe-limitations.json) remain preserved. The v2 pair and independent OS-pipe regression tests verify the fix.

## Dependency security findings

`pip-audit 2.9.0` reported **56 advisory records against Pillow 11.3.0**, potentially sharing aliases; this is not 56 demonstrated reachable exploits. Many concern unused codecs/fonts/raw APIs, but Pillow decodes accepted scans. The [official Pillow 13.0.0 release](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html) was verified, an actual isolated install passed `pip check`, and its actual freeze changed only Pillow. Final-image compatibility, exact synthetic output parity and regressions passed. [Before](performance/dependency-audit-before.json) and [after](performance/dependency-audit.json) retain findings and lookup gaps.

The updated lock lookup reports **0 findings with two CPU-wheel skips**. Separate upstream-version lookup reports **two unresolved torch advisories**: `CVE-2026-4538` (pt2 loading; no listed fix) and [`CVE-2025-3000`](https://github.com/advisories/GHSA-rrmf-rvhw-rf47) (`torch.jit.script`; listed fix 2.13.0). Neither path is invoked: no model/code uploads or pt2 loading, and only the trusted digest is loaded using restricted `weights_only=True`. Isolation reduces exposure, not proof of safety. Torch remains pinned pending compatible stack validation. These findings are open; this is not a clean security certification, OS/native-binary scan or formal penetration test.

## Real gateway/API measurements

Actual loopback client → gateway → Express/MongoDB or Python/SQLite → live authority/worker, with committed audits/persistence and no mocked endpoints or automatic retries. [All samples/statuses](performance/runs/api-1/api.json) and [conditions](performance/runs/api-1/conditions.json) are retained.

| Operation | n | p50 / p95 (ms) |
| --- | --- | --- |
| Login | 5 | 260.70 / 436.01 |
| Live identity | 20 | 19.43 / 72.87 |
| Public availability | 20 | 11.00 / 19.68 |
| Publish slot | 5 | 77.30 / 96.10 |
| Book appointment | 5 | 75.84 / 96.05 |
| Cancel appointment | 4 | 63.93 / 83.88 |
| Assigned audited assessment | 20 | 49.92 / 97.62 |
| Clinical inference + persistence | 10 | 218.62 / 729.96 |
| Patient approved result | 20 | 24.61 / 63.02 |
| Patient private PNG download | 20 | 27.65 / 49.66 |

Point timings (n=1, not useful percentiles): appointment context 91.01 ms, intake 292.77 ms, exact replay 47.62 ms, observations 47.30 ms, PNG upload 59.16 ms, submission 88.40 ms, independent approval 28.78 ms. Sequential clinical inference completed at **3.36/s**. For n≤10, nearest-rank p95 is the observed maximum; these are local synthetic observations, not SLOs or concurrent capacity. Expected 200/201 responses are counted; intentional failures are separate.

Five real API checks passed: intake replay; cross-patient/role denial and malicious PNG rejection; concurrent identical inference sharing one prediction/attempt; approved result/scan integrity and immutable findings; actual logout/revocation denial. Technician assignment remained an explicit private operator action. Results contain no identities, tokens, clinical UUIDs or scan bytes.

## Final verification and limits

Final backend helper: **45 Node**, **110 clinical/protocol Python**, **12 worker** and **4 legacy guards** passed (**126 Python**), plus **2 statistics tests**. Includes actual concurrent inference/busy rejection, malicious/truncated inputs, supervisor death/restart, IPC faults, genuine refused-worker transport with durable failed state/same-request recovery, and all prior ownership/revocation/approval/audit/outage regressions. No skips. Frontend **22 tests**, strict build and npm audits passed. **15 real Chromium journeys passed** on a separate fresh fixture: 11 scheduling/session cases and 4 full clinical/staff cases, including real CPU inference, independent approval, private patient scan access, outage retry and role revocation. The demo was stopped afterward without deleting persistent volumes.

Predictions remain experimental, doctor-only and separate from immutable approved findings. No treatment decisions, hosted AI, cloud deployment, legacy authentication integration or account adoption. Mongo/SQLite remain separate without atomicity claims. Original data/weights/credentials are preserved; only labeled disposable services are cleaned up, never persistent volumes. Existing production TLS/MFA/key/delivery/abuse controls, reconciliation, capped lists, explicit linkage/assignment and emergency-intake UI gaps remain. Worker crashes require explicit restart; exhaustive host-failure, HTTP denial-of-service and long soak testing remain future work.

# MedStroke checkpoint audit and CPU gate — 2026-11-10

Scope: only `ml/MedStroke.pt` from the existing repository, not any patient scan/database. User explicitly confirmed the intended trusted SHA-256 in this session before model deserialization. That confirmation establishes this milestone's artifact trust decision; it does **not** supply missing training provenance or establish clinical validity.

## Non-executing artifact audit

- Size: **2,966,344 bytes**; SHA-256 **200f5ab52415cb96dae577a45b5d1cb8a6dedb2cbab03c32885d826553d0d595**. The original artifact is unchanged and mounted read-only; no replacement/exported model is committed.
- Tracked since initial repository commit `0b22c3d`. README calls it a placeholder; `ml/labels.txt` is empty. No trusted release signature/checksum, training dataset documentation, model card, clinical evaluation or independently established chain of custody exists in this checkout.
- ZIP metadata: 167 entries, 2,943,421 expanded bytes; one 45,240-byte `best/data.pkl`. `zipfile`/`pickletools` inspection did not unpickle/execute checkpoint content.
- Audited pickle global references: Python set/OrderedDict, torch storage/tensor/parameter constructors; torch SiLU/BatchNorm2d/ModuleList/Sequential/Conv2d/Dropout/Linear/AdaptiveAvgPool2d; torchvision Compose/Resize/CenterCrop/ToTensor/Normalize/InterpolationMode; Ultralytics ClassificationModel/Conv/C2f/Bottleneck/Classify. No shell/network/OS execution callable was observed. Static inspection is not a proof that arbitrary future checkpoints are safe.
- Embedded metadata claims save date `2025-10-27T03:24:50.080356`, Ultralytics **8.3.221**, task classify, starting architecture yolov8n-cls, input size 224 and 20 training epochs. These are self-reported metadata, not verified training facts. Embedded license string references AGPL-3.0; no new weight distribution or license substitution is introduced.
- Legacy requirements pin Ultralytics 8.3.0/torch 2.2.0+cpu, inconsistent with the checkpoint metadata. `ml/model_loader.py` calls unrestricted `YOLO(path)` and `ml/predict.py` converts PIL to RGB, calls predict and rounds percentages under a confidence label. Those modules are inspected but never imported by the new services.

## Restricted loading and verified preprocessing

The new worker checks fixed path/no-follow, exact byte count and the confirmed digest **before** deserialization. It uses explicit `torch.load(..., map_location='cpu', weights_only=True)` with the finite reviewed class allowlist, not a dynamically expanded allowlist, arbitrary Python import, unrestricted pickle retry or the legacy YOLO loader. Model type/version/class-name checks fail closed. [PyTorch serialization guidance](https://docs.pytorch.org/docs/stable/notes/serialization) explains restricted loading and its limits; fingerprint approval, reviewed code and container isolation remain separate controls.

Actual restricted loading confirmed embedded class IDs **0 bleeding, 1 ischemia, 2 normal** and the transform:

1. Decode validated synthetic PNG, convert to RGB.
2. Resize shorter side to **224**, bilinear interpolation, antialias enabled.
3. Center crop **224 × 224**.
4. ToTensor: channel-first float, values scaled to **0–1**.
5. Embedded normalization is mean `[0,0,0]`, std `[1,1,1]`, so the explicit worker pipeline omits that identity operation.

The worker constructs this pipeline from code; it does not execute a serialized transform object. Model executes float32, CPU eval/inference mode, two torch threads and one interop thread. Output is the classification head's three softmax values; preserve full raw values, derive the max class without percentage rounding, and validate finite range/sum/class/index consistency. These scores are **not calibrated clinical confidence**.

Runtime: pinned Python 3.12.11 base digest, torch **2.10.0+cpu**, torchvision **0.25.0+cpu**, Ultralytics **8.3.221**, NumPy **2.2.6**, Pillow **11.3.0**. The CPU torch/vision pairing follows the [official version matrix](https://github.com/pytorch/pytorch/wiki/PyTorch-Versions). `inference_worker/requirements.lock` is actual pip freeze from the verified isolated CPU image and constrains subsequent builds; legacy requirements are unchanged.

## Actual CPU gate before API integration

Networkless nonroot container; read-only model/root filesystem; private 64 MiB tmpfs, no capabilities/new privileges, 2 CPUs, 1500 MiB memory and 64 PIDs. Synthetic PNGs are generated from constants, not copied from repository scans. Each job is a fresh isolated child process with a 20-second parent deadline and 12 CPU-second rlimit. Library status output is suppressed. No GPU, hosted call, legacy app import or patient input is available.

| Synthetic pattern | Raw predicted label | Raw max score | Child duration (imports/load/preprocess/forward included) |
| --- | --- | --- | --- |
| Black 64×64 | bleeding | 0.39370256662368774 | 7209.852 ms |
| White 64×64 | normal | 0.3774694502353668 | 7345.568 ms |
| Gradient 64×64 | normal | 0.46912384033203125 | 6473.736 ms |

[Full actual results](medstroke-cpu-probe-v1.json) include every score, input hash, model hash and preprocessing version. They are synthetic smoke evidence, not accuracy/capacity/latency guarantees. The first nonroot import probe failed because the numeric container UID had no passwd username; explicit nonsecret USER/cache settings fixed it. Restricted model loading then succeeded, followed by all three actual CPU executions. API configuration was not enabled before this gate passed.

The private worker also performs a real CPU self-test at every startup and refuses to serve if it fails. Every new job rechecks model bytes; unknown/changed/missing weights never trigger a download, unsafe fallback or placeholder prediction.

## Accuracy and clinical limits

No representative CT/MRI test set, ground truth, patient demographics, acquisition distributions, train/test leakage review, sensitivity/specificity, calibration, subgroup analysis, uncertainty/OOD evaluation or clinical trial is available. Flat patterns have no medical ground truth; even a plausible class string on them is not a correct diagnosis. The classifier is an experimental three-label artifact, not an independently validated stroke assessment system. Input container validation does not establish medical image suitability; restricted PNG support is not DICOM handling.

No output can approve a diagnosis, assess tPA eligibility, prescribe treatment or change an immutable human-approved finding. Patients cannot access prediction records even after doctor acknowledgement/dismissal. Real clinical evaluation/adoption requires separately authorized provenance/data/governance work.

## Milestone 6 provenance refinement

Static source-only notebook inspection identified a potential Kaggle training source and image-wise split code. This is not verified checkpoint lineage or independent evaluation; no stored notebook outputs or real images were used. See [Milestone 6 results](../hospital-milestone-6-verification.md) and [source-cell audit hashes](../performance/provenance.json). The previously confirmed artifact fingerprint and experimental/doctor-only restrictions remain unchanged. Milestone 6 updates the isolated decoder to Pillow 13.0.0 with exact synthetic prediction parity; earlier runtime/timings above are historical evidence, not the new dependency inventory.

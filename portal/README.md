# MedStroke unified portal — Milestone 5B

React/TypeScript uses the existing booking identity authority and clinical APIs. Patients book/cancel appointments and view only their own approved assessments/scans. Assigned technicians capture vitals, NIHSS and private PNGs, then submit. Assigned doctors initiate confirmed-appointment encounters, add notes, independently approve/reject human summaries and review experimental predictions separately. Administrators provision/change/revoke staff with password rechecks; admin status never grants clinical access. Legacy Streamlit authentication remains separate.

## Reproducible synthetic demo

Requires Docker, host Python 3, Git/flock and the previously approved exact model artifact. From the repository root:

```sh
docker build -f inference_worker/Dockerfile -t stroke-inference:milestone4b .
bash scripts/portal-demo.sh start
# Open http://127.0.0.1:4180
```

Startup installs locked packages, runs frontend tests/build/audit and creates labeled disposable services: real Express authority and MongoDB tmpfs replica set, Python clinical API with a fresh temporary v4 SQLite store and the isolated CPU worker. The model is mounted read-only only into the worker, never copied. Existing databases/scans/credentials are not mounted. Startup refuses noncanonical/nonempty synthetic databases. The loopback gateway exposes no worker admission key or internal service URL to the browser. `PORTAL_PORT=4182` can select another loopback port.

Fresh random account passwords are in ignored `.portal-demo/credentials.json` (0600 under a 0700 directory). Read privately; never paste/commit them. Fixture signing/delivery keys are random; no public staff registration or default password is introduced. Patients have explicit synthetic links and a doctor assignment established by private fixture proofs, never name/email/code matching. After a doctor starts an encounter, copy its encounter UUID from assessment detail and explicitly assign the fixture technician:

```sh
bash scripts/portal-demo.sh assign ENCOUNTER_UUID
```

This is a private fixture operator action, not a public self-assignment endpoint. No emergency-intake or general linkage/assignment administration UI is supplied; existing authorized emergency APIs remain available separately.

Staff invitations display a delivery UUID only. A trusted local operator must verify the intended recipient through an independent channel, then run in a private terminal:

```sh
bash scripts/portal-demo.sh deliver DELIVERY_UUID
```

The helper requires a TTY, operator reference and explicit HANDOFF confirmation. It consumes the existing one-time delivery and displays the sensitive token once in that private terminal; never put it in logs, command arguments or URLs. Transfer it privately to the intended recipient, who uses “Recover or activate an account” in the portal. Recovery requests return the same generic message; no public token retrieval exists. This is a local demonstration handoff, not a production mail/SMS delivery implementation.

```sh
bash scripts/portal-demo.sh test
bash scripts/portal-demo.sh stop
```

Tests require the browser image below. Stop verifies ownership labels and removes only this demo's containers/networks and freshly generated credential/control/key files. It never deletes persistent volumes. Screenshots/npm cache remain ignored. Each start creates new accounts, appointments, SQLite records and scans; none are production data.

## Development and verification

```sh
docker build -t stroke-portal-browser:5a -f portal/tests/Dockerfile portal/tests
bash scripts/test-clinical-bridge.sh
# Then start/test/stop as above on fresh fixtures.
```

Actual Chromium tests use the production bundle and real services without route mocks. The browser shares the gateway's network namespace and uses secure-context localhost so WebCrypto works without disabling browser security. Private filesystem fixture controls expire sessions, pause listeners, perform explicit assignments and consume delivery; no corresponding public HTTP endpoint exists.

Optional Node 22 host development: `cd portal && npm ci && npm run dev`. Vite binds 127.0.0.1:4181 and proxies to the synthetic demo at 4180; `BOOKING_PROXY_TARGET=http://127.0.0.1:4182 npm run dev` selects an explicit alternate demo. `npm test` and `npm run build` run component/adapter tests and strict TypeScript/Vite compilation. Never point this demo at existing patient data or put credentials in `VITE_*` settings.

## Security and limitations

JWTs stay in private adapter memory, never browser storage/cookies/URLs/logs. Reload requires sign-in; closing/reloading alone does not revoke the bounded authority session. Live `/me`, focus/30-second checks, expiry timers and 401 cleanup discard private views/stale responses. Current server authorization remains authoritative. Logout clears memory immediately and reports whether server revocation succeeded.

Clinical mutations retain the exact request UUID/body/version in memory until success or definite rejection; an explicit retry reuses it after uncertain failures. Other writes remain disabled while unresolved. Booking creation still has no general backend idempotency key. Approved findings are immutable; predictions remain doctor-only even after acknowledgement, experimental and uncalibrated, never diagnoses, tPA eligibility or treatment instructions. Scan downloads use authenticated audited requests, validated PNG blobs and revoked object URLs, not public paths/bearer URLs.

Discovery lists are bounded (clinical/staff 100, scheduling 200) without pagination. Appointment intake retains the existing bounded reservation/retry protocol, not cross-database atomicity or background reconciliation. No automatic account adoption, emergency intake UI, notifications, production delivery, TLS/MFA/key-management rollout, clinical validation or complete accessibility certification is provided. See [5B results](../docs/hospital-milestone-5b-verification.md).

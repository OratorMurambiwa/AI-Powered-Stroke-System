# MedStroke unified portal — Milestone 5A

A real React/TypeScript application for the shared booking identity, patient appointments and doctor scheduling. Technician/admin navigation includes actual self-session controls; clinical and staff-management screens remain for 5B. The portal never calls the clinical API/model worker or displays predictions.

## Reproducible isolated demo

From a checkout of AI-Powered-Stroke-System, with Docker, host Python 3 and Git/flock available:

```sh
bash scripts/portal-demo.sh start
```

Open **http://127.0.0.1:4180**. Startup installs the actual locked frontend/backend packages, runs frontend tests/build/audit, creates a new labeled private Docker network and **tmpfs-only MongoDB replica set**, then serves the production React bundle through a same-origin gateway to the real Express API. It refuses a nonempty fixture database or noncanonical synthetic URI. No existing database, volume, scan, credential or model is adopted. Backend and frontend build artifacts are ignored. Runtime mounts only compiled backend/dependencies, compiled frontend and the fixture server file; it cannot access clinical source databases/scans/weights.

New random credentials for patient, other patient, doctor, technician and admin are written locally to **`.portal-demo/credentials.json`**, mode **0600**, under an ignored mode-0700 directory. Read this file privately; never paste or commit it. There are no fixed passwords or production default accounts. Signing/delivery keys are freshly generated inside the fixture process and never sent to the browser or written into that file. Direct active staff seeding is an explicitly synthetic fixture, not a production provisioning path. New patient registration uses the actual public patient-only authority.

`PORTAL_PORT=4182 bash scripts/portal-demo.sh start` changes the loopback-only demo port. Startup refuses existing recorded demo state; it never stops another service to claim a port. To stop **only this recorded/labeled demo**:

```sh
bash scripts/portal-demo.sh stop
```

Stop removes its disposable tmpfs containers/network and freshly generated credential/control files; it never deletes persistent volumes or normal services. Sanitized screenshots may remain in the ignored demo directory. A stopped demo's disposable appointments/accounts are not retained as clinical data; start creates fresh synthetic fixtures.

## Development

Optional host development requires Node 22.12–22.x and npm; the Docker demo needs no host Node installation. With the isolated demo running:

```sh
cd portal
npm ci
npm run dev
```

Vite binds **127.0.0.1:4181** with a strict port, proxies `/api` to the demo at 127.0.0.1:4180, and makes no browser-visible internal-hostname request. `BOOKING_PROXY_TARGET=http://127.0.0.1:4182 npm run dev` selects an explicitly started alternate **synthetic** demo. Never point this milestone at existing patient/production data. Proxy settings are server-side configuration; no `VITE_*` secret or internal service credential exists.

`npm test` runs component/adapter tests; `npm run build` runs strict TypeScript and Vite production compilation. Actual generated npm lock records the resolved versions; no root/legacy dependency lock changes.

## Browser and full regression verification

```sh
docker build -t stroke-portal-browser:5a -f portal/tests/Dockerfile portal/tests
bash scripts/portal-demo.sh test
bash scripts/portal-demo.sh stop
# Existing trusted inference image is required by the prior full regression harness.
docker build -f inference_worker/Dockerfile -t stroke-inference:milestone4b .
bash scripts/test-clinical-bridge.sh
```

Browser tooling stays separate from runtime. Actual Chromium drives the production bundle and real Express/MongoDB; no route mocks are used. Screenshots remain ignored under `.portal-demo`. Test-only expiry/HTTP-listener pause/resume controls use a private fixture file, never an HTTP endpoint or production identity change. All build/test scripts share the existing Git-local backend installation lock where relevant.

See [5A verification](../docs/hospital-milestone-5a-verification.md) for actual counts and limitations.

## Security and contract boundary

JWTs live only in a private in-memory adapter field, with no local/session storage, IndexedDB, service worker, cookie, URL, log or frontend credentials. Reloading closes the local session view and requires sign-in. Closing/refreshing is **not** server revocation: the bounded authority session remains until expiry or explicit logout-all. Every login/register result is validated through live `GET /api/v1/identity/me`; login's user role and JWT claims are not used to authorize navigation. Session expiry/401 clears state, aborts stale requests and removes private screens. Focus/30-second checks detect revocation even while idle. Backend authorization remains authoritative.

Server logout is attempted while local memory clears immediately. If the server is unreachable, the UI explicitly says local logout succeeded but server revocation could not be confirmed; it does not claim a revoked session. Mutations are never automatically retried; an unconfirmed transport response tells users to refresh records first. Appointment creation has no backend idempotency key yet.

The client validates current response shapes/ownership, escapes all server strings through React text, uses same-origin fetch with credentials omitted, bounded requests and no caching, and rejects unexpected identities/data. Role routes are UX guards; server ownership/role checks remain mandatory. The only backend change is global `Cache-Control: no-store` on API responses. The demo gateway adds a restrictive CSP, no-referrer/nosniff/no-store, serves only compiled assets and proxies only the existing booking API. It is a local demo gateway, not a production deployment architecture.

Patient bookings use appointment UUID v1 creation/cancellation, with the existing native-ID list and legacy cancellation fallback for records lacking a historical UUID. No UUID backfill, account linkage or migration occurs. Availability and lists use existing capped APIs, all times explicitly UTC. Available doctors are derived from published slots, not an invented directory or credential-verification claim. Backend conflict/overlap/past-time/assessment-lock rules are never reimplemented in the browser.

Remaining for 5B: explicitly authorized clinical linkage/capture and approved-result views; doctor-only experimental prediction review without patient leakage; staff provisioning/revocation/recovery UI; paging/active doctor directory and scheduling timezone policy; broader browser/accessibility review and production TLS/gateway/key/abuse-protection work. Preserved clinical protections must remain authoritative.

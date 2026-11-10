# Booking backend — integration milestone 1

Adapted from [OratorMurambiwa/Hospital-booking-system](https://github.com/OratorMurambiwa/Hospital-booking-system/tree/2114faa0bc21eb759b7728eb0194867d679b9c70). The upstream repository is preserved. See [the integration plan](../docs/hospital-integration-plan.md) for the source audit, boundaries and follow-up work.

## Build and verify

Requires Node 22 and MongoDB 8 replica-set support. MongoDB standalone does not support the transactions used here. No patient database, scans or credentials are needed for testing.

```sh
cd booking-backend
npm ci
npm run build
cd ..
# Docker alone can run the real integration suite:
bash booking-backend/scripts/test-docker.sh
```

The Docker helper creates its own private network and tmpfs replica set, with no host ports or persistent volumes. It removes only its own containers/network. Test records use `example.test` emails, synthetic names and dates in 2099. The helper installs locked dependencies and runs HTTP tests against actual Mongoose/MongoDB transactions and indexes. `npm test` also builds, and requires the dedicated `TEST_MONGODB_URI`; it refuses a default database. One failure-injection scenario replaces appointment creation to verify actual transaction rollback; the concurrency tests use real database writes.

For local manual development, provision a **new synthetic-only** replica-set database, copy `.env.example` to ignored `.env`, and generate a private random `JWT_SECRET` (32 bytes minimum). Run `npm run dev` or `npm run build && npm start`. The server binds loopback. It fails startup if the secret is missing, MongoDB is standalone, or required indexes cannot initialize. No Redis service is required. CORS is disabled until an explicit portal origin is chosen. No external model or notification provider is called.

## API

- `POST /api/auth/register`: `{email, password, name, role?: "patient"}`. Only patient signup; passwords need 12 characters and at most 72 UTF-8 bytes. Doctor/admin roles require operator provisioning outside public endpoints; no production provisioning UI exists yet.
- `POST /api/auth/login`: `{email, password}`. Returns a signed expiring token. Use `Authorization: Bearer TOKEN`; authorization reads the current persisted role. No refresh/recovery flow yet.
- `GET /api/availability`: optional `doctorId`, `date=YYYY-MM-DD`, `availableOnly=true|false`.
- Doctor only: `POST /api/availability` and `PUT /api/availability/:id` with complete `{date, startTime: "HH:mm", endTime: "HH:mm"}`. `DELETE /api/availability/:id` removes an owned, unbooked slot. No request may set `isBooked`.
- Patient only: `POST /api/appointments` with `{availabilityId, notes?}`. Patient/doctor identity and schedule are server-owned. One confirmed appointment per slot is enforced by a partial unique index and atomic slot claiming inside a retried transaction.
- `GET /api/appointments`: own appointments for patients/doctors; admins may list all. Optional `status` and `date` filters.
- `PATCH /api/appointments/:id/cancel`: owning patient/doctor only, confirmed appointments only; cancellation and slot release are atomic. Cancelling an older cancelled appointment cannot release a replacement booking.
- `GET /api/health`: database connection readiness.

Dates/times use **UTC** for this prototype, including day filters. Intervals are half-open (`[start,end)`), cannot cross midnight and must start in the future. Overlapping doctor availability is rejected, including concurrent creation/update through this API. Schedule writes serialize on a persisted doctor record, not a process-local mutex. Only doctors may own availability; admins do not become doctors automatically. List responses are capped at 200; pagination and hospital timezone handling are planned.

Caching and the upstream simulated email/SMS workers are intentionally omitted from the integrated copy: cached reads can become stale, notifications were only log messages, and post-commit Redis errors could misreport successful bookings. Responses do not promise email delivery. Implement a transactional notification outbox before introducing a real sender.

No clinical prediction or treatment endpoint is added. This backend is not yet connected to Streamlit/SQLite. Clinical outputs remain experimental and require clinician review. This is a synthetic local prototype, not a production hospital system.

# Milestone 5A verification — 2026-11-10

Baseline: `bcc4423e8e9be2a367ca41f50947203b90ef8080`. Scope: a working unified React/TypeScript scheduling portal against the existing identity/booking authority, not clinical UI or a separate authentication system. See [launch/development/test instructions](../portal/README.md) and [integration plan](hospital-integration-plan.md).

## Executed final results

| Check | Actual result |
| --- | --- |
| Frontend component/adapter suite | **16 passed**, 2 files: 7 component and 9 adapter/security cases; controlled transport, not claimed as real backend evidence |
| Frontend production build | Strict TypeScript compile and Vite build passed; final JS 243.11 kB / gzip 75.70 kB, CSS 10.92 kB / gzip 3.32 kB |
| Frontend dependency audit | `npm ci` with actual generated lock; `npm audit`: **0 reported vulnerabilities** |
| Real Chromium journeys | **11 passed**, production React bundle + real Express authority/booking APIs + private tmpfs MongoDB replica set; no route mocks |
| Existing Node backend/identity | **44 TAP tests passed**, zero failures/skips (42 child scenarios + 2 parent tests) |
| Existing Python clinical/protocol/integration | **104 passed**, including 81 actual authority/clinical integration cases |
| Existing isolated CPU model worker | **4 passed**, real inference/invalid input/hash/deadline/recovery cases |
| Existing legacy signup/default-user guards | **4 passed** |
| Total existing Python regressions | **112 passed**; the 11 browser journeys are reported separately, not used to inflate that count |
| Static/artifact checks | Shell syntax, Python AST parse, package/lock JSON, `git diff --check`, bundle/config marker review and staged secret/artifact checks passed |

Final execution used `bash scripts/test-clinical-bridge.sh`, then a fresh `bash scripts/portal-demo.sh start`, `test`, `stop`. The last demo launch reran frontend tests/build/audit and all 11 browser journeys after source formatting with pinned temporary Prettier 3.6.2; it used the final sources and narrowed runtime mounts. Demo cleanup completed without deleting persistent volumes or normal services. Desktop 1440px and mobile 390px screenshots were inspected; mobile has no horizontal overflow. Screenshots remain ignored and contain synthetic fixtures only.

Runtime: Node **22.14.0** / npm **10.9.2**; actual frontend lock resolves React/React DOM **19.3.1**, TypeScript **7.0.2**, Vite **8.3.7**, Vitest **5.1.0**, Testing Library React **16.3.3** and jsdom **29.1.1**. Browser tooling: Playwright Python **1.55.0**, Chromium **140.0.7339.16** in the separate repository-owned test image. MongoDB remains the existing pinned **8.0.17** replica-set image. Host Node is absent; all JavaScript build/test commands ran inside Docker. The optional host development path is documented but was not separately exercised.

An initial complete-regression attempt stopped at the prior model worker's readiness/CPU startup gate; **it is not success evidence**. A separate unchanged bounded networkless CPU probe passed (7260.853 ms), and the unchanged full harness subsequently passed all 44 Node/112 Python cases. No execution/resource limit, checkpoint trust gate or model/clinical code was weakened. The first readiness failure's root cause was not established; investigate recurrence as an operational reliability issue. A previous 14-test/9-browser frontend pass preceded the added calendar/login-race/keyboard/logout-all coverage; only the final 16/11 counts above describe the final portal.

## Real browser/API evidence

The fixture seeds **only a newly empty marked synthetic MongoDB** at its exact private hostname/database URI. Passwords and signing/delivery keys use fresh random values; real signed sessions are obtained through ordinary HTTP login. The React bundle calls the actual APIs through a same-origin gateway. The tests drive browser forms, not a mock role switch or prefilled token store.

1. Patient registration through the real public authority creates a patient session/dashboard. Browser localStorage/sessionStorage and cookies are empty; refresh requires sign-in.
2. A patient books an actual published slot through appointment v1, sees the confirmed appointment, and cancels through the real API. The committed server status is checked. A second patient sees no first-patient appointment and receives 404 for its identifier. Patient availability publication receives 403. Private appointment responses have `Cache-Control: no-store`.
3. Doctor publishes, edits and removes owned future availability through the UI; resulting slots appear/change/disappear from actual server responses.
4. Doctor sees the real assigned patient booking; booked slot edit/delete controls are disabled. Doctor cancellation succeeds through the existing authoritative transaction.
5. Logout clears the UI and invalidates the actual captured server JWT; a later API request using it returns 401. The token exists only in test process memory for this assertion, not an artifact/log.
6. A **private fixture-only database expiration** changes the stored session to past expiry; a protected browser refresh receives actual server 401, removes private content and shows the expired-session notice. This is not a claim that the test waited out 15 natural minutes or changed production token TTL.
7. A signed-in patient navigating to the doctor route sees a forbidden workspace. Actual technician/admin logins show the correct navigation/account controls and receive server 403 for appointment reads. No clinical or prediction UI appears.
8. Private fixture control stops the real API HTTP listener while the static gateway stays live. Refresh shows service-unavailable state and no retained appointment rows; restarting that listener and refreshing restores real records. This is an actual local service outage, not a mocked HTTP route or physical database failure.
9. Invalid real credentials show an actionable sign-in error; real overlapping doctor availability produces a conflict. Patient/doctor layouts render at 390px with no horizontal overflow; protected navigation/logout remains usable.
10. Keyboard Tab/Enter signs in through real forms and navigates to account/security.
11. Logout-all invalidates a second independently signed-in browser session; its next protected request removes private content with the ended-session notice.

The separate component/adapter tests cover closed live principal contracts, ignored login role claims, patient-only registration payloads, forbidden routes/staff data-fetch isolation, escaped untrusted doctor names, empty/loading/error/recovery states, malformed calendar data, wrong-owner responses, 401 cleanup, stale response rejection, conflict/ambiguous transport without retries and local logout despite server failure. Review also found/fixed an authentication race: an older failed login can no longer clear a newer successfully verified session. A specific deferred-response test proves that behavior. These controlled transports do not replace the real browser evidence.

## Security, isolation and preservation

JWTs are private in-memory adapter fields, never local/session storage, cookies, IndexedDB, service workers, URLs or application logs. The portal uses live `/me`, bounded session timers, focus/30-second validation, and current server authorization. Every new user/session remounts private views; abort/generation checks discard prior-session responses. Login's role field/JWT claims are never an authority, and no role picker or separate credential database exists.

No automatic mutation retry or optimistic fake success is introduced. Buttons disable while pending; transport uncertainty instructs refresh before retry. Logout clears local access immediately and truthfully reports failure to confirm server revocation. Closing/reloading alone does not revoke the retained bounded server session; it requires a new sign-in locally. Requests use same-origin relative paths, credentials omitted, no-store and rejected redirects. All UI strings render as escaped React text, with labels, landmarks, status/alert regions, native form validation, visible keyboard focus and reduced-motion styling. These are implemented/tested accessibility features, not a complete WCAG or assistive-technology certification.

The backend's only behavior change is `Cache-Control: no-store` for API routes; identity/booking business and ownership logic remain unchanged. Booking uses v1 UUID creation/cancellation and the existing owned native-ID list, with legacy cancellation fallback for pre-UUID records. No UUID/backfill, account linkage or clinical migration occurs. The demo gateway has same-origin API proxying, restrictive CSP, no-referrer/nosniff/no-store and compiled-assets-only serving.

The demo runtime mounts only compiled backend/dependencies, compiled frontend and the exact fixture server file, plus its new private fixture directory. It cannot access clinical databases, original uploaded scans or model weights. Direct synthetic active staff fixtures are confined to this empty exact-URI demo, not a public staff registration or production provisioning mechanism. Private expire/pause/resume controls are filesystem-only, never HTTP endpoints. Fresh random credentials are mode 0600 in ignored mode-0700 `.portal-demo`; stop removes those new files. No existing credential or persistent volume is deleted. Docker cleanup verifies strict run-name and ownership labels before removing only its own containers/network.

The final bundle was checked against actual newly generated synthetic passwords and internal key/configuration markers; none were present. It has no generated source maps or hosted font/asset/model requests. Dependency/build outputs, screenshots, logs, fixture controls/credentials and DB files remain ignored. Review/staging includes source, actual npm lock, tests and documentation only.

The historical `data/`, `ml/`, clinical API, inference worker, legacy source and dependency locks are unchanged. Existing clinical review/approval/experimental-prediction protections passed regression. The **portal** never requests scans, clinical records or predictions, calls hosted AI, invokes legacy authentication or provides treatment controls. The old regression suites still perform their explicitly synthetic real CPU tests; they are distinct from portal behavior. Original Hospital-booking-system and unrelated IncidentIQ work remain untouched.

## Launch and Milestone 5B

From the stroke repository root: **`bash scripts/portal-demo.sh start`**, then **http://127.0.0.1:4180**. Read its locally generated credential file privately. `stop` removes only that disposable demo. Optional Node 22 host development uses `cd portal && npm ci && npm run dev` at localhost:4181, proxying the separately running synthetic demo. See [full instructions](../portal/README.md). The final verified demo was stopped so publication leaves no extra application service running.

5B should add explicitly assigned clinical capture/linkage, immutable clinician-approved patient-result views, doctor-only experimental prediction review without patient leakage, and audited staff provisioning/revocation/recovery UI. Technician/admin 5A workspaces deliberately provide identity/session foundation rather than pretending those workflows exist.

Remaining scheduling limits: public slots form the available-doctor list, not a complete verified/active directory; stale/revoked clinician slots can still be listed but booking rechecks live clinician state. Existing APIs cap lists at 200 without pagination. UTC is explicit; hospital timezone/DST, patient overlap policy, booking idempotency, notification delivery and post-intake cancellation/reassignment need domain work. No real patient adoption is authorized.

Production TLS/gateway/CSP review, key management/MFA/distributed throttling, broader browser/screen-reader/accessibility evaluation and operational model-startup reliability remain work. The demo gateway and fixture seeder are local tools, not a production deployment. Training provenance/clinical accuracy remains unverified, and all classifier/treatment logic stays experimental and separate from this portal.

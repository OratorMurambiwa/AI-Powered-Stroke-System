import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  ApiClient,
  ApiError,
  StaleSession,
  message,
  type Principal,
  type Slot,
  type Appointment,
  type Schedule,
} from "./api";

const names = {
  patient: "Patient",
  doctor: "Doctor",
  technician: "Technician",
  admin: "Administrator",
};
function navigate(path: string) {
  history.pushState(null, "", path);
  dispatchEvent(new PopStateEvent("popstate"));
}
function Link({
  to,
  children,
  ...props
}: {
  to: string;
  children: ReactNode;
  className?: string;
  "aria-current"?: "page";
}) {
  return (
    <a
      href={to}
      {...props}
      onClick={(e) => {
        if (!e.metaKey && !e.ctrlKey && !e.shiftKey && e.button === 0) {
          e.preventDefault();
          navigate(to);
        }
      }}
    >
      {children}
    </a>
  );
}
function Banner({ error }: { error: unknown }) {
  return error ? (
    <div className="alert" role="alert">
      {message(error)}
    </div>
  ) : null;
}
function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty">
      <span aria-hidden="true">＋</span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function DateLine({
  date,
  startTime,
  endTime,
}: {
  date: string;
  startTime: string;
  endTime: string;
}) {
  return (
    <>
      <strong>
        {new Intl.DateTimeFormat("en", {
          month: "short",
          day: "numeric",
          year: "numeric",
          timeZone: "UTC",
        }).format(new Date(date + "T00:00:00Z"))}
      </strong>
      <span>
        {startTime} – {endTime} UTC
      </span>
    </>
  );
}

function AuthForm({
  api,
  register,
  onSuccess,
  disabled = false,
}: {
  api: ApiClient;
  register: boolean;
  onSuccess: (p: Principal) => void;
  disabled?: boolean;
}) {
  const [error, setError] = useState<unknown>(),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy || disabled) return;
    const data = new FormData(e.currentTarget);
    setError(undefined);
    setBusy(true);
    try {
      onSuccess(
        await api.authenticate(register ? "register" : "login", {
          email: String(data.get("email")),
          password: String(data.get("password")),
          ...(register ? { name: String(data.get("name")) } : {}),
        }),
      );
    } catch (e) {
      if (!(e instanceof StaleSession)) setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-layout">
      <section className="auth-story">
        <p className="eyebrow">CONNECTED CARE, SIMPLY</p>
        <h1>
          Your next step.
          <br />A clearer path to care.
        </h1>
        <p>
          Appointments and care teams in one secure place. Make time for what
          matters.
        </p>
        <div className="story-card">
          <span className="story-icon" aria-hidden="true">
            ✚
          </span>
          <div>
            <strong>Built around your visit</strong>
            <p>
              Find a published appointment, manage your schedule and stay
              connected.
            </p>
          </div>
        </div>
        <p className="small">Synthetic demonstration · No real patient care</p>
      </section>
      <section className="auth-card" aria-labelledby="auth-title">
        <p className="eyebrow">MEDSTROKE CARE PORTAL</p>
        <h2 id="auth-title">
          {register ? "Create your patient account" : "Welcome back"}
        </h2>
        <p>
          {register
            ? "Register securely with our shared identity service."
            : "Sign in with your hospital account to continue."}
        </p>
        <Banner error={error} />
        <form onSubmit={submit} aria-busy={busy}>
          {register && (
            <label>
              Full name
              <input name="name" autoComplete="name" maxLength={120} required />
            </label>
          )}
          <label>
            Email address
            <input
              name="email"
              type="email"
              autoComplete="username"
              required
              maxLength={254}
            />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              required
              minLength={register ? 12 : undefined}
              maxLength={72}
              aria-describedby={register ? "password-hint" : undefined}
            />
          </label>
          {register && (
            <p id="password-hint" className="hint">
              At least 12 characters; maximum 72 UTF-8 bytes. Registration
              creates a patient account only.
            </p>
          )}
          <button className="primary wide" disabled={busy || disabled}>
            {busy
              ? "Connecting…"
              : register
                ? "Create patient account"
                : "Sign in"}
          </button>
        </form>
        <p className="auth-switch">
          {register ? "Already have an account? " : "New to the portal? "}
          <Link to={register ? "/login" : "/register"}>
            {register ? "Sign in" : "Register as a patient"}
          </Link>
        </p>
        <p className="hint">
          Staff accounts are provisioned through the authorized hospital
          identity process. Refreshing this page signs you out.
        </p>
      </section>
    </div>
  );
}

function BookingDashboard({
  api,
  principal,
}: {
  api: ApiClient;
  principal: Principal;
}) {
  const doctor = principal.role === "doctor";
  const [slots, setSlots] = useState<Slot[]>([]),
    [appointments, setAppointments] = useState<Appointment[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState<unknown>();
  const [revision, setRevision] = useState(0),
    [status, setStatus] = useState(""),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const [confirm, setConfirm] = useState<Appointment | null>(null),
    [editing, setEditing] = useState<Slot | null>(null);
  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(undefined);
    setSlots([]);
    setAppointments([]);
    Promise.all([
      api.slots(doctor ? principal.subject : undefined),
      api.appointments(principal, status),
    ])
      .then(([s, a]) => {
        if (current) {
          setSlots(s);
          setAppointments(a);
        }
      })
      .catch((e) => {
        if (current && !(e instanceof StaleSession)) setError(e);
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [api, principal.sessionId, revision, status, doctor, principal.subject]);
  async function action(work: () => Promise<void>, success: string) {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    setNotice("");
    try {
      await work();
      setConfirm(null);
      setEditing(null);
      setNotice(success);
      setRevision((v) => v + 1);
    } catch (e) {
      if (!(e instanceof StaleSession)) setError(e);
    } finally {
      setBusy(false);
    }
  }
  const groups = Array.from(new Set(slots.map((s) => s.doctorId)));
  async function publish(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const schedule: Schedule = {
      date: String(f.get("date")),
      startTime: String(f.get("startTime")),
      endTime: String(f.get("endTime")),
    };
    await action(
      () => api.publish(schedule, editing?.id),
      editing ? "Availability updated." : "Availability published.",
    );
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            {doctor ? "YOUR PRACTICE" : "YOUR CARE, CONNECTED"}
          </p>
          <h1>{doctor ? "Manage your day." : "Let’s plan your next visit."}</h1>
          <p>
            {doctor
              ? "Publish time for your patients and keep track of your assigned visits."
              : "Find a care team and manage your appointments in one place."}
          </p>
        </div>
        <button
          className="secondary"
          disabled={busy || loading}
          onClick={() => setRevision((v) => v + 1)}
        >
          Refresh records
        </button>
      </div>
      <Banner error={error} />
      {notice && (
        <p className="success" role="status">
          {notice}
        </p>
      )}
      {loading ? (
        <div className="loading" role="status">
          Loading your schedule…
        </div>
      ) : (
        <>
          <div className="stats">
            <div>
              <span>
                {doctor ? "Assigned appointments" : "Your appointments"}
              </span>
              <strong>{appointments.length}</strong>
              <small>In the current view</small>
            </div>
            <div>
              <span>{doctor ? "Published slots" : "Available doctors"}</span>
              <strong>{doctor ? slots.length : groups.length}</strong>
              <small>
                {doctor
                  ? "Your published schedule"
                  : "With published availability"}
              </small>
            </div>
            <div className="stat-note">
              <span className="status-dot" />{" "}
              <strong>One secure identity</strong>
              <small>
                Access is checked by the hospital service on every request.
              </small>
            </div>
          </div>
          <div className="dashboard-grid">
            <section
              className="panel"
              id="appointments"
              aria-labelledby="appointments-title"
            >
              <div className="panel-head">
                <div>
                  <p className="eyebrow">SCHEDULE</p>
                  <h2 id="appointments-title">
                    {doctor ? "Assigned appointments" : "My appointments"}
                  </h2>
                </div>
                <label className="compact">
                  Status
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                  >
                    <option value="">All statuses</option>
                    <option value="confirmed">Confirmed</option>
                    <option value="cancelled">Cancelled</option>
                    <option value="completed">Completed</option>
                  </select>
                </label>
              </div>
              {appointments.length === 0 ? (
                <Empty title="No appointments here yet">
                  {doctor
                    ? "Your assigned appointments will appear here when patients book."
                    : "Choose a published time below to book your next visit."}
                </Empty>
              ) : (
                <ul className="record-list">
                  {appointments.map((a) => (
                    <li className="appointment" key={a.id}>
                      <div className="date-block">
                        <DateLine {...a} />
                      </div>
                      <div className="record-main">
                        <h3>{doctor ? a.patientName : a.doctorName}</h3>
                        <p>
                          {doctor
                            ? "Assigned patient"
                            : "Appointment with your care team"}
                        </p>
                        <span className={"badge " + a.status}>{a.status}</span>
                      </div>
                      {a.status === "confirmed" && (
                        <div className="record-action">
                          {confirm?.id === a.id ? (
                            <div
                              className="confirmation"
                              role="group"
                              aria-label="Confirm cancellation"
                            >
                              <p>Cancel this appointment?</p>
                              <button
                                className="danger"
                                disabled={busy}
                                onClick={() =>
                                  void action(
                                    () => api.cancel(a),
                                    "Appointment cancelled.",
                                  )
                                }
                              >
                                Confirm cancellation
                              </button>
                              <button
                                className="text-button"
                                disabled={busy}
                                onClick={() => setConfirm(null)}
                              >
                                Keep appointment
                              </button>
                            </div>
                          ) : (
                            <button
                              className="text-button"
                              disabled={busy}
                              onClick={() => setConfirm(a)}
                            >
                              Cancel appointment
                            </button>
                          )}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <aside className="care-note">
              <div className="care-mark" aria-hidden="true">
                ✚
              </div>
              <p className="eyebrow">A LITTLE CLARITY</p>
              <h2>Care starts with a conversation.</h2>
              <p>
                All times are shown in UTC. If your visit already has an
                assessment in progress, cancellation may require staff review.
              </p>
              <hr />
              <p className="small">
                This portal is a synthetic demonstration. It does not provide
                emergency services, diagnoses or treatment recommendations.
              </p>
            </aside>
          </div>
          {doctor && (
            <section className="panel" aria-labelledby="publish-title">
              <div className="panel-head">
                <div>
                  <p className="eyebrow">AVAILABILITY</p>
                  <h2 id="publish-title">
                    {editing ? "Edit available slot" : "Publish a time slot"}
                  </h2>
                </div>
                {editing && (
                  <button
                    className="text-button"
                    onClick={() => setEditing(null)}
                  >
                    Stop editing
                  </button>
                )}
              </div>
              <form
                key={editing?.id || "new"}
                className="schedule-form"
                onSubmit={publish}
              >
                <label>
                  Date (UTC)
                  <input
                    type="date"
                    name="date"
                    defaultValue={editing?.date}
                    required
                  />
                </label>
                <label>
                  Start time (UTC)
                  <input
                    type="time"
                    name="startTime"
                    defaultValue={editing?.startTime}
                    required
                  />
                </label>
                <label>
                  End time (UTC)
                  <input
                    type="time"
                    name="endTime"
                    defaultValue={editing?.endTime}
                    required
                  />
                </label>
                <button className="primary" disabled={busy}>
                  {busy
                    ? "Saving…"
                    : editing
                      ? "Save slot"
                      : "Publish availability"}
                </button>
              </form>
              <p className="hint">
                The server checks future times, overlap and ownership. Booked
                slots cannot be edited or removed.
              </p>
            </section>
          )}
          <section
            className="panel"
            id="availability"
            aria-labelledby="availability-title"
          >
            <div className="panel-head">
              <div>
                <p className="eyebrow">
                  {doctor ? "YOUR PUBLISHED TIMES" : "FIND CARE"}
                </p>
                <h2 id="availability-title">
                  {doctor
                    ? "My availability"
                    : "Available doctors & appointments"}
                </h2>
              </div>
              <span className="subtle">Times in UTC</span>
            </div>
            {slots.length === 0 ? (
              <Empty
                title={
                  doctor ? "No published slots" : "No published times available"
                }
              >
                {doctor
                  ? "Publish a future time slot using the form above."
                  : "Try refreshing later. New availability appears when doctors publish it."}
              </Empty>
            ) : (
              <div className="slots-grid">
                {(doctor ? [principal.subject] : groups).map((id) => (
                  <div className="doctor-card" key={id}>
                    <div className="doctor-heading">
                      <div className="avatar" aria-hidden="true">
                        {slots
                          .find((s) => s.doctorId === id)
                          ?.doctorName.slice(0, 1)}
                      </div>
                      <div>
                        <h3>
                          {slots.find((s) => s.doctorId === id)?.doctorName}
                        </h3>
                        <p>
                          {doctor
                            ? "Your schedule"
                            : "Published appointment times"}
                        </p>
                      </div>
                    </div>
                    {slots
                      .filter((s) => s.doctorId === id)
                      .map((s) => (
                        <div className="slot" key={s.id}>
                          <div className="date-block">
                            <DateLine {...s} />
                            {doctor && (
                              <span
                                className={
                                  "badge " +
                                  (s.isBooked ? "confirmed" : "available")
                                }
                              >
                                {s.isBooked ? "Booked" : "Available"}
                              </span>
                            )}
                          </div>
                          {doctor ? (
                            <div className="slot-buttons">
                              <button
                                className="secondary"
                                disabled={busy || s.isBooked}
                                onClick={() => {
                                  setEditing(s);
                                  document
                                    .getElementById("publish-title")
                                    ?.scrollIntoView({ block: "center" });
                                }}
                              >
                                Edit slot
                              </button>
                              <button
                                className="text-button"
                                disabled={busy || s.isBooked}
                                onClick={() =>
                                  void action(
                                    () => api.remove(s.id),
                                    "Availability removed.",
                                  )
                                }
                              >
                                Remove slot
                              </button>
                            </div>
                          ) : (
                            <button
                              className="primary"
                              disabled={busy}
                              onClick={() =>
                                void action(
                                  () => api.book(s.id),
                                  "Appointment booked.",
                                )
                              }
                            >
                              {busy ? "Please wait…" : "Book appointment"}
                            </button>
                          )}
                        </div>
                      ))}
                  </div>
                ))}
              </div>
            )}
          </section>
          <p className="hint">
            Showing up to 200 appointments and 200 published time slots. Use
            status filters or contact your care team if a record is missing.
          </p>
        </>
      )}
    </>
  );
}
function Account({
  api,
  principal,
  logout,
}: {
  api: ApiClient;
  principal: Principal;
  logout: (all?: boolean) => void;
}) {
  const [count, setCount] = useState<number>(),
    [error, setError] = useState<unknown>();
  useEffect(() => {
    let active = true;
    api
      .sessions()
      .then((n) => {
        if (active) setCount(n);
      })
      .catch((e) => {
        if (active && !(e instanceof StaleSession)) setError(e);
      });
    return () => {
      active = false;
    };
  }, [api]);
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR ACCOUNT</p>
          <h1>Secure access, in your hands.</h1>
          <p>
            Your shared hospital identity is managed by the identity authority.
          </p>
        </div>
      </div>
      <Banner error={error} />
      <section className="panel account">
        <h2>Session & access</h2>
        <dl>
          <dt>Current role</dt>
          <dd>{names[principal.role]}</dd>
          <dt>Session expires</dt>
          <dd>
            {new Date(principal.expiresAt * 1000).toLocaleTimeString("en", {
              timeZone: "UTC",
            })}{" "}
            UTC
          </dd>
          <dt>Active sessions</dt>
          <dd>
            {count === undefined
              ? "Loading…"
              : count === 100
                ? "100 or more"
                : count}
          </dd>
        </dl>
        <p>
          Credentials stay in memory on this device. Refreshing or closing this
          page requires a new sign-in.
        </p>
        <button className="secondary" onClick={() => logout(true)}>
          Sign out all sessions
        </button>
      </section>
    </>
  );
}
export function App({ client }: { client?: ApiClient }) {
  const [api] = useState(() => client || new ApiClient()),
    [person, setPerson] = useState<Principal | null>(null),
    [path, setPath] = useState(location.pathname),
    [notice, setNotice] = useState(""),
    [connection, setConnection] = useState(""),
    [signingOut, setSigningOut] = useState(false);
  useEffect(() => {
    const listener = () => setPath(location.pathname);
    addEventListener("popstate", listener);
    api.onExpired = () => {
      setPerson(null);
      setNotice("Your session ended. Sign in again.");
      setConnection("");
      navigate("/login");
    };
    return () => {
      removeEventListener("popstate", listener);
      api.clear();
    };
  }, [api]);
  useEffect(() => {
    if (!person) return;
    const expire = () => {
      api.clear();
      api.onExpired();
    };
    const timer = setTimeout(
      expire,
      Math.max(0, person.expiresAt * 1000 - Date.now()),
    );
    let active = true;
    const verify = () => {
      if (Date.now() >= person.expiresAt * 1000) {
        expire();
        return;
      }
      void api
        .me()
        .then((next) => {
          if (active) {
            if (
              next.subject !== person.subject ||
              next.sessionId !== person.sessionId
            ) {
              expire();
              return;
            }
            setPerson(next);
            setConnection("");
          }
        })
        .catch((e) => {
          if (active && e instanceof ApiError && e.status >= 500)
            setConnection(
              "The identity service is unavailable. Refresh or try again shortly.",
            );
        });
    };
    const heartbeat = setInterval(verify, 30000);
    addEventListener("focus", verify);
    return () => {
      active = false;
      clearTimeout(timer);
      clearInterval(heartbeat);
      removeEventListener("focus", verify);
    };
  }, [api, person?.sessionId, person?.expiresAt]);
  async function logout(all = false) {
    const pending = api.logout(all);
    setPerson(null);
    setSigningOut(true);
    setConnection("");
    setNotice("Signing out…");
    navigate("/login");
    try {
      await pending;
      setNotice("You have been signed out.");
    } catch (e) {
      setNotice(message(e));
    } finally {
      setSigningOut(false);
    }
  }
  const home = person ? "/" + person.role : "/login";
  const allowed = person && (path === home || path === "/account");
  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <div className="demo-bar">
        SYNTHETIC DEMONSTRATION{" "}
        <span>Appointments in UTC · No real patient care</span>
      </div>
      <header className="topbar">
        <Link to={home} className="brand">
          <span aria-hidden="true">✚</span>
          <div>
            MedStroke<small>CARE PORTAL</small>
          </div>
        </Link>
        <div className="header-right">
          {person ? (
            <>
              <span className="role-label">{names[person.role]} workspace</span>
              <button className="secondary" onClick={() => void logout()}>
                Sign out
              </button>
            </>
          ) : (
            <span className="subtle">One account. Connected care.</span>
          )}
        </div>
      </header>
      {notice && (
        <div className="global-notice" role="status">
          {notice}
        </div>
      )}
      {connection && (
        <div className="alert" role="alert">
          {connection}
        </div>
      )}
      <div className={person ? "app-shell" : ""}>
        {person && (
          <nav className="sidebar" aria-label="Main navigation">
            <p className="eyebrow">WORKSPACE</p>
            <Link to={home} aria-current={path === home ? "page" : undefined}>
              {person.role === "patient"
                ? "Appointments"
                : person.role === "doctor"
                  ? "Practice & schedule"
                  : names[person.role] + " workspace"}
            </Link>
            <Link
              to="/account"
              aria-current={path === "/account" ? "page" : undefined}
            >
              Account & security
            </Link>
            <div className="nav-note">
              <span aria-hidden="true">◇</span>
              <p>
                Access follows your current hospital role. Your care team’s
                service checks every request.
              </p>
            </div>
          </nav>
        )}
        <main
          id="main"
          className={person ? "workspace" : "auth-main"}
          key={person?.sessionId || "guest"}
        >
          {!person ? (
            <AuthForm
              key={path}
              api={api}
              register={path === "/register"}
              disabled={signingOut}
              onSuccess={(p) => {
                setPerson(p);
                setNotice("");
                navigate("/" + p.role);
              }}
            />
          ) : !allowed ? (
            <section className="panel forbidden">
              <p className="eyebrow">ACCESS RESTRICTED</p>
              <h1>This workspace is not available to your account.</h1>
              <p>Your hospital role determines which services you can use.</p>
              <Link to={home}>Return to your workspace</Link>
            </section>
          ) : path === "/account" ? (
            <Account
              api={api}
              principal={person}
              logout={(all) => void logout(all)}
            />
          ) : person.role === "patient" || person.role === "doctor" ? (
            <BookingDashboard api={api} principal={person} />
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">
                    {names[person.role].toUpperCase()} WORKSPACE
                  </p>
                  <h1>Welcome to your care portal.</h1>
                  <p>
                    Your shared identity is active. Clinical and
                    staff-management screens are not yet available in this
                    portal.
                  </p>
                </div>
              </div>
              <section className="panel">
                <h2>
                  {person.role === "technician"
                    ? "Assessment workspace"
                    : "Identity administration"}
                </h2>
                <p>
                  {person.role === "technician"
                    ? "Use the authorized clinical workflow for your assigned assessments."
                    : "Staff access continues to be managed through authorized hospital processes."}
                </p>
                <p>
                  No clinical records, scans or experimental predictions are
                  displayed in this portal.
                </p>
                <Link to="/account">Manage your account & security</Link>
              </section>
            </>
          )}
        </main>
      </div>
      <footer>
        MedStroke care portal{" "}
        <span>
          Secure scheduling foundation · Experimental clinical services remain
          separate
        </span>
      </footer>
    </>
  );
}

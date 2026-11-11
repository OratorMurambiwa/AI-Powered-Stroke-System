import { useEffect, useState, type FormEvent } from "react";
import {
  ApiClient,
  ApiError,
  StaleSession,
  message,
  type Principal,
} from "./api";
interface Staff {
  id: string;
  name: string;
  email: string;
  role: string;
  state: string;
}
export function Admin({ api, person }: { api: ApiClient; person: Principal }) {
  const [rows, setRows] = useState<Staff[]>([]),
    [error, setError] = useState<unknown>(),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [revision, setRevision] = useState(0),
    [selected, setSelected] = useState<Staff | null>(null),
    [events, setEvents] = useState<{ action: string; at: string }[]>([]);
  useEffect(() => {
    let active = true;
    setError(undefined);
    api
      .identity("staff")
      .then((raw) => {
        const v = raw as { schemaVersion: number; staff: Staff[] };
        if (
          v?.schemaVersion !== 1 ||
          !Array.isArray(v.staff) ||
          v.staff.length > 100 ||
          v.staff.some(
            (r) =>
              !r ||
              !/^[a-f0-9]{24}$/.test(r.id) ||
              !["doctor", "technician", "admin"].includes(r.role) ||
              typeof r.name !== "string" ||
              typeof r.email !== "string" ||
              !["active", "invited", "revoked"].includes(r.state),
          )
        )
          throw new ApiError(503, "Unexpected staff directory.");
        if (active) setRows(v.staff);
      })
      .catch((e) => {
        if (active && !(e instanceof StaleSession)) setError(e);
      });
    return () => {
      active = false;
    };
  }, [api, revision]);
  async function perform(path: string, method: string, body: unknown) {
    setBusy(true);
    setError(undefined);
    setNotice("");
    try {
      const raw = (await api.identity(path, method, body)) as {
        deliveryId?: string;
      };
      setNotice(
        raw.deliveryId
          ? "Staff invitation created. Awaiting activation. Delivery ID: " +
              raw.deliveryId +
              ". An authorized operator must verify the recipient and perform secure handoff."
          : "Staff security change recorded. Existing sessions and stale clinical permissions are invalidated.",
      );
      setSelected(null);
      setEvents([]);
      setRevision((r) => r + 1);
    } catch (e) {
      if (!(e instanceof StaleSession)) setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function provision(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget,
      f = new FormData(form);
    const body = {
      name: f.get("name"),
      email: f.get("email"),
      role: f.get("role"),
      currentPassword: f.get("currentPassword"),
      reason: f.get("reason"),
    };
    form.reset();
    await perform("staff", "POST", body);
  }
  async function change(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selected) return;
    const f = new FormData(e.currentTarget),
      revoke = f.get("operation") === "revoke";
    const body = {
      currentPassword: f.get("currentPassword"),
      reason: f.get("reason"),
      ...(revoke ? {} : { role: f.get("role") }),
    };
    e.currentTarget.reset();
    await perform(
      "staff/" + selected.id + (revoke ? "/revoke" : "/role"),
      revoke ? "POST" : "PATCH",
      body,
    );
  }
  async function audit(staff: Staff) {
    setSelected(staff);
    setEvents([]);
    setError(undefined);
    try {
      const v = (await api.identity("staff/" + staff.id + "/audit")) as {
        schemaVersion: number;
        events: { action: string; at: string }[];
      };
      if (
        v.schemaVersion !== 1 ||
        !Array.isArray(v.events) ||
        v.events.some(
          (r) => typeof r.action !== "string" || typeof r.at !== "string",
        )
      )
        throw new ApiError(503, "Unexpected audit response.");
      setEvents(v.events);
    } catch (e) {
      if (!(e instanceof StaleSession)) setError(e);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">IDENTITY ADMINISTRATION</p>
          <h1>Staff access & security</h1>
          <p>
            Clinical access is never granted by administrator status. Staff
            invitation and changes require password recheck and an authorization
            reason.
          </p>
        </div>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => setRevision((r) => r + 1)}
        >
          Refresh staff
        </button>
      </div>
      {Boolean(error) && (
        <p className="alert" role="alert">
          {message(error)}
        </p>
      )}
      {notice && (
        <p className="success" role="status">
          {notice}
        </p>
      )}
      <section className="panel">
        <h2>Staff directory</h2>
        <ul className="record-list">
          {rows.map((r) => (
            <li className="appointment" key={r.id}>
              <div className="record-main">
                <strong>{r.name}</strong>
                <p>
                  {r.email} · {r.role} · {r.state}
                </p>
              </div>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => void audit(r)}
              >
                Manage {r.name}
              </button>
            </li>
          ))}
        </ul>
        <p className="hint">
          Up to 100 staff identities. Patients are not listed or promoted.
        </p>
      </section>
      <section className="panel">
        <h2>Invite staff</h2>
        <form className="clinical-fields" onSubmit={(e) => void provision(e)}>
          <label>
            Staff name
            <input name="name" required maxLength={120} />
          </label>
          <label>
            Staff email
            <input name="email" type="email" required />
          </label>
          <label>
            Staff role
            <select name="role" aria-label="Staff role">
              <option value="doctor">Doctor</option>
              <option value="technician">Technician</option>
              <option value="admin">Administrator</option>
            </select>
          </label>
          <label>
            Your current password
            <input
              name="currentPassword"
              type="password"
              autoComplete="current-password"
              required
            />
          </label>
          <label>
            Authorization reason
            <input name="reason" required maxLength={500} />
          </label>
          <button className="primary" disabled={busy}>
            Invite staff member
          </button>
        </form>
        <p className="hint">
          No password or activation token is returned here. The recipient
          chooses a password after verified private handoff.
        </p>
      </section>
      {selected && (
        <section className="panel">
          <h2>Manage staff identity: {selected.name}</h2>
          <p>
            {selected.state} · {selected.role}
          </p>
          <form onSubmit={(e) => void change(e)}>
            <fieldset
              disabled={
                busy ||
                selected.state === "revoked" ||
                selected.id === person.subject
              }
            >
              <label>
                Security operation
                <select name="operation" aria-label="Security operation">
                  <option value="role">
                    Change role (invalidates sessions)
                  </option>
                  <option value="revoke">Revoke staff access</option>
                </select>
              </label>
              <label>
                New staff role
                <select
                  name="role"
                  aria-label="New staff role"
                  defaultValue={selected.role}
                >
                  <option value="doctor">Doctor</option>
                  <option value="technician">Technician</option>
                  <option value="admin">Administrator</option>
                </select>
              </label>
              <label>
                Confirm your current password
                <input
                  name="currentPassword"
                  type="password"
                  autoComplete="current-password"
                  required
                />
              </label>
              <label>
                Change authorization reason
                <input name="reason" required maxLength={500} />
              </label>
              <label className="check-label">
                <input type="checkbox" required />I am authorized to make this
                security change.
              </label>
              <button className="danger">Apply staff security change</button>
            </fieldset>
          </form>
          {selected.id === person.subject && (
            <p>Self-role changes and self-revocation are not permitted.</p>
          )}
          <h3>Identity audit history</h3>
          <ul>
            {events.map((e, i) => (
              <li key={i}>
                {e.action} — {e.at}
              </li>
            ))}
          </ul>
        </section>
      )}
      <section className="panel">
        <h2>Secure recovery procedure</h2>
        <p>
          Use the account recovery form for a generic recovery request. An
          authorized operator must independently verify the registered recipient
          and use the existing one-time private delivery procedure.
          Administrators cannot view passwords or bypass activation/recovery
          proof.
        </p>
      </section>
    </>
  );
}
export function Recovery({ api }: { api: ApiClient }) {
  const [error, setError] = useState<unknown>(),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>, reset: boolean) {
    e.preventDefault();
    const form = e.currentTarget,
      f = new FormData(form);
    const body = reset
      ? { token: f.get("token"), newPassword: f.get("newPassword") }
      : { email: f.get("email") };
    form.reset();
    setBusy(true);
    setError(undefined);
    try {
      await api.recover(body, reset);
      setNotice(
        reset
          ? "Password updated. Sign in again."
          : "If recovery is available, instructions will be delivered through the registered channel.",
      );
    } catch (e) {
      if (!(e instanceof StaleSession)) setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="auth-card recovery-card">
      <p className="eyebrow">ACCOUNT SECURITY</p>
      <h1>Recover or activate your account</h1>
      {Boolean(error) && (
        <p role="alert" className="alert">
          {message(error)}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <h2>Request recovery</h2>
      <form onSubmit={(e) => void submit(e, false)}>
        <label>
          Registered email
          <input name="email" type="email" required autoComplete="username" />
        </label>
        <button className="primary" disabled={busy}>
          Request recovery instructions
        </button>
      </form>
      <h2>Complete verified recovery or activation</h2>
      <p>
        Paste the single-use token provided through the verified private
        channel. Tokens expire and are never accepted in a URL.
      </p>
      <form onSubmit={(e) => void submit(e, true)}>
        <label>
          Private activation or recovery token
          <input
            name="token"
            type="password"
            autoComplete="off"
            required
            minLength={64}
            maxLength={64}
          />
        </label>
        <label>
          New password
          <input
            name="newPassword"
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            maxLength={72}
          />
        </label>
        <button className="primary" disabled={busy}>
          Set new password
        </button>
      </form>
      <a href="/login">Return to sign in</a>
    </section>
  );
}

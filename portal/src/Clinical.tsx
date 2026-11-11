import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiClient,
  ApiError,
  StaleSession,
  message,
  type Principal,
  type Appointment,
} from "./api";
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const states = ["DRAFT", "SUBMITTED", "APPROVED", "REJECTED"];
type Dict = Record<string, unknown>;
function obj(v: unknown): Dict {
  if (!v || typeof v !== "object" || Array.isArray(v))
    throw new ApiError(503, "Unexpected clinical response. Refresh records.");
  return v as Dict;
}
function identifier(v: unknown): string {
  if (typeof v !== "string" || !uuid.test(v))
    throw new ApiError(503, "Unexpected clinical identifier.");
  return v;
}
interface Encounter {
  encounterId: string;
  patientId: string;
  state: string;
  version: number;
}
interface Scan {
  scanId: string;
  sha256: string;
  size: number;
}
interface Assessment {
  encounterId: string;
  version: number;
  state: string;
  summary: string | null;
  reviewedAt: string | null;
  observations: {
    vitals: Dict | null;
    nihss: Dict | null;
    observedAt?: string;
    notes?: { text: string; at: string }[];
    scans: Scan[];
  };
}
export function assessment(value: unknown, patient: boolean): Assessment {
  const v = obj(value),
    o = obj(v.observations);
  const expected = [
    "schemaVersion",
    "encounterId",
    "version",
    "state",
    "experimental",
    "inferencePerformed",
    "clinicianReviewRequired",
    "summary",
    "reviewedBy",
    "reviewedAt",
    "observations",
    ...(patient ? [] : ["history"]),
  ];
  if (
    Object.keys(v).sort().join(",") !== expected.sort().join(",") ||
    v.clinicianReviewRequired !== true ||
    !(v.summary === null || typeof v.summary === "string") ||
    !(v.reviewedAt === null || typeof v.reviewedAt === "string") ||
    (!patient && (!Array.isArray(v.history) || v.history.length > 128))
  )
    throw new ApiError(503, "Invalid assessment contract.");
  if (
    o.notes !== undefined &&
    (!Array.isArray(o.notes) ||
      o.notes.some(
        (n) => !n || typeof n.text !== "string" || typeof n.at !== "string",
      ))
  )
    throw new ApiError(503, "Invalid internal note response.");

  if (
    v.schemaVersion !== 1 ||
    !states.includes(String(v.state)) ||
    !Number.isInteger(v.version) ||
    v.experimental !== true ||
    v.inferencePerformed !== false ||
    !Array.isArray(o.scans) ||
    o.scans.length > 16
  )
    throw new ApiError(503, "Unexpected assessment response.");
  if (
    patient &&
    (v.state !== "APPROVED" ||
      "history" in v ||
      "notes" in o ||
      Object.keys(o).some(
        (k) => !["vitals", "nihss", "scans", "observedAt"].includes(k),
      ))
  )
    throw new ApiError(503, "Unapproved clinical content was withheld.");
  for (const s of o.scans) {
    const scan = obj(s);
    identifier(scan.scanId);
    if (
      scan.mediaType !== "image/png" ||
      typeof scan.size !== "number" ||
      !Number.isInteger(scan.size) ||
      scan.size < 1 ||
      scan.size > 1048576
    )
      throw new ApiError(503, "Invalid scan metadata.");
    if (typeof scan.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(scan.sha256))
      throw new ApiError(503, "Invalid scan metadata.");
  }
  for (const key of ["vitals", "nihss"])
    if (o[key] !== null) {
      const data = obj(o[key]);
      for (const n of Object.values(data))
        if (typeof n !== "number" || !Number.isFinite(n))
          throw new ApiError(503, "Invalid observation response.");
    }
  identifier(v.encounterId);
  return v as unknown as Assessment;
}
const vitalFields = [
  ["systolicMmHg", "Systolic BP (mmHg)"],
  ["diastolicMmHg", "Diastolic BP (mmHg)"],
  ["pulseBpm", "Pulse (bpm)"],
  ["temperatureC", "Temperature (°C)"],
  ["oxygenPercent", "Oxygen saturation (%)"],
  ["glucoseMgDl", "Glucose (mg/dL)"],
];
const nihssFields = [
  ["consciousness", 3],
  ["questions", 2],
  ["commands", 2],
  ["gaze", 2],
  ["visual", 3],
  ["facial", 3],
  ["leftArm", 4],
  ["rightArm", 4],
  ["leftLeg", 4],
  ["rightLeg", 4],
  ["ataxia", 2],
  ["sensory", 2],
  ["language", 3],
  ["dysarthria", 2],
  ["neglect", 2],
] as const;
export function StartAssessment({
  api,
  appointment,
}: {
  api: ApiClient;
  appointment: Appointment;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(),
    [done, setDone] = useState(Boolean(appointment.encounterId));
  const pending = useRef<unknown>(undefined);
  async function start() {
    if (!appointment.uuid) return;
    setBusy(true);
    setError(undefined);
    try {
      if (!pending.current) {
        const c = obj(
          await api.clinical("appointment-context/" + appointment.uuid),
        );
        if (c.schemaVersion !== 1 || c.appointmentId !== appointment.uuid)
          throw new ApiError(503, "Unexpected appointment context.");
        pending.current = {
          schemaVersion: 1,
          requestId: appointment.assessmentRequestId || crypto.randomUUID(),
          sourceId: identifier(c.sourceId),
          patientId: identifier(c.patientId),
          patientMappingId: identifier(c.patientMappingId),
          clinicianMappingId: identifier(c.clinicianMappingId),
        };
      }
      const result = obj(
        await api.startAssessment(appointment.uuid, pending.current),
      );
      if (result.state === "CREATED") setDone(true);
      else if (result.state === "PENDING")
        setError(
          new ApiError(
            503,
            "Intake is pending. Retry this same request; cancellation remains reserved.",
          ),
        );
      else
        throw new ApiError(
          409,
          "Intake was rejected. Review the appointment mapping with an operator.",
        );
    } catch (e) {
      if (!(e instanceof StaleSession)) setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="intake-control">
      {done ? (
        <a
          href="/clinical"
          onClick={(e) => {
            e.preventDefault();
            history.pushState(null, "", "/clinical");
            dispatchEvent(new PopStateEvent("popstate"));
          }}
        >
          View assigned assessment
        </a>
      ) : (
        <button
          className="secondary"
          disabled={busy || !appointment.uuid}
          onClick={() => void start()}
        >
          {busy
            ? "Starting…"
            : pending.current || appointment.assessmentRequestId
              ? "Retry assessment intake"
              : "Start assessment"}
        </button>
      )}
      {Boolean(error) && <p role="alert">{message(error)}</p>}
    </div>
  );
}
function Download({
  api,
  encounter,
  scan,
}: {
  api: ApiClient;
  encounter: string;
  scan: Scan;
}) {
  const [error, setError] = useState<unknown>(),
    [busy, setBusy] = useState(false);
  const active = useRef(true);
  const urls = useRef(new Set<string>());
  useEffect(
    () => () => {
      active.current = false;
      for (const u of urls.current) URL.revokeObjectURL(u);
    },
    [],
  );
  async function download() {
    setBusy(true);
    setError(undefined);
    try {
      const blob = await api.scan(encounter, scan.scanId);
      if (!active.current) return;
      const url = URL.createObjectURL(blob);
      urls.current.add(url);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = scan.scanId + ".png";
      anchor.click();
      setTimeout(() => {
        URL.revokeObjectURL(url);
        urls.current.delete(url);
      }, 1000);
    } catch (e) {
      if (active.current && !(e instanceof StaleSession)) setError(e);
    } finally {
      if (active.current) setBusy(false);
    }
  }
  return (
    <div>
      <button
        className="secondary"
        disabled={busy}
        onClick={() => void download()}
      >
        {busy ? "Downloading…" : "Download PNG scan"}
      </button>
      <small>
        {" "}
        {scan.sha256.slice(0, 12)} · {scan.size} bytes
      </small>
      {Boolean(error) && <p role="alert">{message(error)}</p>}
    </div>
  );
}
export function Clinical({
  api,
  person,
}: {
  api: ApiClient;
  person: Principal;
}) {
  const [list, setList] = useState<Encounter[]>([]),
    [selected, setSelected] = useState(""),
    [revision, setRevision] = useState(0),
    [error, setError] = useState<unknown>(),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(undefined);
    setList([]);
    api
      .clinical("workspace")
      .then((raw) => {
        const v = obj(raw);
        if (
          v.schemaVersion !== 1 ||
          !Array.isArray(v.encounters) ||
          v.encounters.length > 100
        )
          throw new ApiError(503, "Unexpected workspace response.");
        const items = v.encounters.map((raw) => {
          const r = obj(raw);
          identifier(r.encounterId);
          identifier(r.patientId);
          if (
            !states.includes(String(r.state)) ||
            !Number.isInteger(r.version) ||
            (person.role === "patient" && r.state !== "APPROVED")
          )
            throw new ApiError(503, "Unauthorized workspace content withheld.");
          return r as unknown as Encounter;
        });
        if (active) {
          setList(items);
          if (!items.some((i) => i.encounterId === selected)) setSelected("");
        }
      })
      .catch((e) => {
        if (active && !(e instanceof StaleSession)) setError(e);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [api, person.sessionId, revision]);
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CLINICAL CARE</p>
          <h1>
            {person.role === "patient"
              ? "Your approved assessments"
              : "Assigned assessment workspace"}
          </h1>
          <p>
            {person.role === "patient"
              ? "Only independently clinician-approved results are available here."
              : "Observations and independent clinical review. Experimental predictions remain a separate doctor-only record."}
          </p>
        </div>
        <button className="secondary" onClick={() => setRevision((r) => r + 1)}>
          Refresh clinical records
        </button>
      </div>
      {Boolean(error) && (
        <p className="alert" role="alert">
          {message(error)}
        </p>
      )}
      {loading ? (
        <p role="status">Loading clinical records…</p>
      ) : (
        <>
          <section className="panel">
            <h2>
              {person.role === "patient"
                ? "Approved results"
                : "Your assigned encounters"}
            </h2>
            {!list.length ? (
              <p>
                No accessible assessments yet.{" "}
                {person.role !== "patient" &&
                  "New encounters require an explicit assignment."}
              </p>
            ) : (
              <ul className="record-list">
                {list.map((e) => (
                  <li key={e.encounterId} className="appointment">
                    <div>
                      <strong>Encounter {e.encounterId.slice(0, 8)}</strong>
                      <p className="hint">
                        {e.state} · revision {e.version}
                      </p>
                    </div>
                    <button
                      className="secondary"
                      onClick={() => setSelected(e.encounterId)}
                    >
                      Open assessment
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
          {selected && (
            <EncounterView
              key={selected}
              api={api}
              person={person}
              encounter={selected}
            />
          )}
        </>
      )}
    </>
  );
}
function EncounterView({
  api,
  person,
  encounter,
}: {
  api: ApiClient;
  person: Principal;
  encounter: string;
}) {
  const [data, setData] = useState<Assessment>(),
    [predictions, setPredictions] = useState<Dict[]>([]),
    [error, setError] = useState<unknown>(),
    [busy, setBusy] = useState(false),
    [revision, setRevision] = useState(0),
    [notice, setNotice] = useState("");
  const mounted = useRef(true);
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );
  const pending = useRef<{ path: string; body: unknown } | null>(null);
  const [hasPending, setHasPending] = useState(false);
  const path = "encounters/" + encounter;
  useEffect(() => {
    let active = true;
    setData(undefined);
    setError(undefined);
    Promise.all([
      api.clinical(path + "/assessment"),
      person.role === "doctor"
        ? api.clinical(path + "/predictions")
        : Promise.resolve(null),
    ])
      .then(([raw, p]) => {
        const result = assessment(raw, person.role === "patient");
        if (result.encounterId !== encounter)
          throw new ApiError(503, "Mismatched encounter.");
        let rows: Dict[] = [];
        if (p) {
          const v = obj(p);
          if (
            v.schemaVersion !== 1 ||
            v.patientVisible !== false ||
            !Array.isArray(v.predictions)
          )
            throw new ApiError(503, "Unexpected prediction response.");
          rows = v.predictions.map((x) => {
            const r = obj(x);
            identifier(r.predictionId);
            if (r.experimental !== true || r.patientVisible !== false)
              throw new ApiError(503, "Unlabeled prediction withheld.");
            if (r.prediction) {
              const pred = obj(r.prediction);
              if (
                pred.patientVisible !== false ||
                pred.experimental !== true ||
                typeof pred.rawScore !== "number" ||
                !Number.isFinite(pred.rawScore) ||
                pred.rawScore < 0 ||
                pred.rawScore > 1 ||
                !["bleeding", "ischemia", "normal"].includes(
                  String(pred.predictedClass),
                )
              )
                throw new ApiError(503, "Invalid experimental prediction.");
            }
            return r;
          });
        }
        if (active) {
          setData(result);
          setPredictions(rows);
        }
      })
      .catch((e) => {
        if (active && !(e instanceof StaleSession)) setError(e);
      });
    return () => {
      active = false;
    };
  }, [api, encounter, revision, person.role]);
  async function execute(command: { path: string; body: unknown }) {
    if (!mounted.current || (pending.current && pending.current !== command))
      return;
    setBusy(true);
    setError(undefined);
    setNotice("");
    pending.current = command;
    setHasPending(true);
    try {
      const r = obj(await api.clinical(command.path, "POST", command.body));
      if (r.state === "PENDING") {
        setNotice(
          "Inference remains pending. Retry the same action to check its outcome.",
        );
      } else {
        pending.current = null;
        setHasPending(false);
        setNotice("Clinical action recorded.");
      }
      setRevision((r) => r + 1);
    } catch (e) {
      if (!(e instanceof StaleSession)) {
        setError(e);
        if (e instanceof ApiError && e.status < 500) {
          pending.current = null;
          setHasPending(false);
        }
      }
    } finally {
      setBusy(false);
    }
  }
  function mutate(action: string, payload: unknown) {
    if (!mounted.current || !data || busy || pending.current) return;
    void execute({
      path: path + "/assessment",
      body: {
        schemaVersion: 1,
        requestId: crypto.randomUUID(),
        expectedVersion: data.version,
        action,
        data: payload,
      },
    });
  }
  async function observations(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const vitals: Dict = {},
      nihss: Dict = {};
    for (const [key] of vitalFields) vitals[key] = Number(f.get(key));
    for (const [key] of nihssFields) nihss[key] = Number(f.get(key));
    mutate("OBSERVATIONS", {
      vitals,
      nihss,
      observedAt: new Date(String(f.get("observedAt")) + "Z").toISOString(),
    });
  }
  async function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const file = f.get("scan") as File;
    if (!file || !file.size || file.size > 1048576) {
      setError(new ApiError(413, "Choose a PNG scan no larger than 1 MiB."));
      return;
    }
    const buffer = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (const n of buffer) binary += String.fromCharCode(n);
    mutate("SCAN", { mediaType: "image/png", contentBase64: btoa(binary) });
    e.currentTarget?.reset();
  }
  const locked = busy || hasPending;
  const editable = data && ["DRAFT", "REJECTED"].includes(data.state);
  return (
    <section className="panel clinical-detail">
      <div className="panel-head">
        <div>
          <p className="eyebrow">ENCOUNTER {encounter.slice(0, 8)}</p>
          <h2>Assessment detail</h2>
          <p className="hint">Encounter reference: {encounter}</p>
        </div>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => setRevision((r) => r + 1)}
        >
          Refresh assessment
        </button>
      </div>
      {Boolean(error) && (
        <p className="alert" role="alert">
          {message(error)}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {hasPending && (
        <button
          className="secondary"
          disabled={busy}
          onClick={() => pending.current && void execute(pending.current)}
        >
          Retry pending action
        </button>
      )}
      {!data ? (
        <p role="status">Loading assessment…</p>
      ) : (
        <>
          <p className="badge confirmed">
            {data.state} · revision {data.version}
          </p>
          {data.summary && (
            <section className="clinical-summary">
              <h3>
                {person.role === "patient"
                  ? "Clinician-approved summary"
                  : "Review summary"}
              </h3>
              <p>{data.summary}</p>
              <p className="hint">Reviewed {data.reviewedAt}</p>
            </section>
          )}
          <h3>Recorded observations</h3>
          {data.observations.vitals ? (
            <dl className="observation-grid">
              {Object.entries(data.observations.vitals).map(([k, v]) => (
                <div key={k}>
                  <dt>{vitalFields.find(([key]) => key === k)?.[1] || k}</dt>
                  <dd>{String(v)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p>No vitals recorded.</p>
          )}
          <p className="hint">
            Observed at {data.observations.observedAt || "not recorded"}
          </p>
          {data.observations.nihss && (
            <details>
              <summary>NIHSS component observations</summary>
              <dl className="observation-grid">
                {Object.entries(data.observations.nihss).map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>{String(v)}</dd>
                  </div>
                ))}
              </dl>
            </details>
          )}
          <h3>Private scans</h3>
          {!data.observations.scans.length ? (
            <p>No scans recorded.</p>
          ) : (
            data.observations.scans.map((scan) => (
              <Download
                key={scan.scanId}
                api={api}
                encounter={encounter}
                scan={scan}
              />
            ))
          )}
          {person.role !== "patient" && (
            <>
              <section>
                <h3>Capture vitals & NIHSS</h3>
                <form onSubmit={(e) => void observations(e)}>
                  <fieldset disabled={locked || !editable}>
                    <label>
                      Observed at (UTC)
                      <input
                        name="observedAt"
                        type="datetime-local"
                        required
                        step="60"
                      />
                    </label>
                    <div className="clinical-fields">
                      {vitalFields.map(([key, label]) => (
                        <label key={key}>
                          {label}
                          <input
                            name={key}
                            type="number"
                            step="any"
                            required
                            defaultValue={
                              data.observations.vitals?.[key] as
                                | number
                                | undefined
                            }
                          />
                        </label>
                      ))}
                    </div>
                    <h4>NIHSS components (raw observations)</h4>
                    <div className="clinical-fields">
                      {nihssFields.map(([key, max]) => (
                        <label key={key}>
                          NIHSS {key}
                          <input
                            name={key}
                            type="number"
                            min={0}
                            max={max}
                            required
                            defaultValue={
                              data.observations.nihss?.[key] as
                                | number
                                | undefined
                            }
                          />
                        </label>
                      ))}
                    </div>
                    <button className="primary">Record observations</button>
                  </fieldset>
                </form>
              </section>
              <form onSubmit={(e) => void upload(e)}>
                <fieldset disabled={locked || !editable}>
                  <label>
                    PNG scan (maximum 1 MiB)
                    <input
                      name="scan"
                      type="file"
                      accept="image/png,.png"
                      required
                    />
                  </label>
                  <p className="hint">
                    The service validates actual PNG contents. Do not upload
                    real patient scans.
                  </p>
                  <button className="secondary">Upload PNG</button>
                </fieldset>
              </form>
              <button
                className="primary"
                disabled={locked || !editable}
                onClick={() => mutate("SUBMIT", {})}
              >
                Submit assessment
              </button>
              {person.role === "doctor" && (
                <>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const f = new FormData(e.currentTarget);
                      mutate("NOTE", { text: String(f.get("note")) });
                      e.currentTarget.reset();
                    }}
                  >
                    <fieldset disabled={locked || !editable}>
                      <label>
                        Internal clinical note
                        <textarea name="note" maxLength={2000} required />
                      </label>
                      <button className="secondary">Add clinical note</button>
                    </fieldset>
                  </form>
                  {data.observations.notes?.map((note, i) => (
                    <p className="internal-note" key={i}>
                      {note.text}
                    </p>
                  ))}
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const native = e.nativeEvent as SubmitEvent;
                      const action = (native.submitter as HTMLButtonElement)
                        ?.value;
                      const f = new FormData(e.currentTarget);
                      mutate(action, {
                        summary: String(f.get("summary")),
                        attested: f.get("attested") === "on",
                      });
                    }}
                  >
                    <fieldset disabled={locked || data.state !== "SUBMITTED"}>
                      <label>
                        Independent clinical summary / rejection reason
                        <textarea name="summary" maxLength={4000} required />
                      </label>
                      <label className="check-label">
                        <input name="attested" type="checkbox" required />I
                        independently reviewed these observations. This decision
                        does not automatically approve any AI prediction.
                      </label>
                      <button
                        className="primary"
                        name="decision"
                        value="APPROVE"
                      >
                        Approve assessment
                      </button>
                      <button className="danger" name="decision" value="REJECT">
                        Reject assessment
                      </button>
                    </fieldset>
                  </form>
                  <section className="prediction-panel">
                    <p className="eyebrow">DOCTOR ONLY · EXPERIMENTAL</p>
                    <h3>Experimental AI predictions</h3>
                    <p>
                      Uncalibrated model scores are not diagnoses, tPA
                      eligibility or treatment advice. Acknowledgement never
                      changes approved clinical findings or patient visibility.
                    </p>
                    {data.observations.scans.map((scan) => (
                      <button
                        key={scan.scanId}
                        className="secondary"
                        disabled={locked}
                        onClick={() =>
                          void execute({
                            path: path + "/predictions",
                            body: {
                              schemaVersion: 1,
                              requestId: crypto.randomUUID(),
                              scanId: scan.scanId,
                            },
                          })
                        }
                      >
                        Run experimental inference
                      </button>
                    ))}
                    {predictions.map((r) => (
                      <div
                        className="prediction-record"
                        key={String(r.predictionId)}
                      >
                        <p>
                          {String(r.state)} · attempt {String(r.attempts)}
                        </p>
                        {Boolean(r.prediction) && (
                          <>
                            <strong>
                              Experimental label:{" "}
                              {String(obj(r.prediction).predictedClass)}
                            </strong>
                            <p>
                              Raw score: {String(obj(r.prediction).rawScore)}{" "}
                              (not clinical confidence)
                            </p>
                            <p className="hint">
                              Model SHA-256:{" "}
                              {String(obj(r.prediction).modelSha256)}
                              <br />
                              Input SHA-256:{" "}
                              {String(obj(r.prediction).scanSha256)}
                            </p>
                          </>
                        )}
                        {r.review ? (
                          <p>
                            Doctor review: {String(obj(r.review).decision)} —{" "}
                            {String(obj(r.review).note)}
                          </p>
                        ) : (
                          r.state === "SUCCEEDED" && (
                            <form
                              onSubmit={(e) => {
                                e.preventDefault();
                                const f = new FormData(e.currentTarget);
                                void execute({
                                  path:
                                    path +
                                    "/predictions/" +
                                    String(r.predictionId) +
                                    "/review",
                                  body: {
                                    schemaVersion: 1,
                                    requestId: crypto.randomUUID(),
                                    expectedReviewVersion: 0,
                                    decision: f.get("decision"),
                                    note: f.get("reviewNote"),
                                    attested: true,
                                  },
                                });
                              }}
                            >
                              <fieldset disabled={locked}>
                                <label>
                                  Experimental prediction review note
                                  <textarea
                                    name="reviewNote"
                                    required
                                    maxLength={2000}
                                  />
                                </label>
                                <label>
                                  Review decision
                                  <select name="decision">
                                    <option value="ACKNOWLEDGED">
                                      Acknowledged (not a diagnosis)
                                    </option>
                                    <option value="DISMISSED">Dismissed</option>
                                  </select>
                                </label>
                                <label className="check-label">
                                  <input type="checkbox" required />I reviewed
                                  this experimental output separately from
                                  clinical findings.
                                </label>
                                <button className="secondary">
                                  Record prediction review
                                </button>
                              </fieldset>
                            </form>
                          )
                        )}
                      </div>
                    ))}
                  </section>
                </>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}

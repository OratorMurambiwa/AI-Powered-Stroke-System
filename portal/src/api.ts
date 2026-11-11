export type Role = "patient" | "doctor" | "technician" | "admin";
export interface Principal {
  schemaVersion: 1;
  issuer: string;
  subject: string;
  role: Role;
  sessionId: string;
  expiresAt: number;
}
export interface Slot {
  id: string;
  doctorId: string;
  doctorName: string;
  date: string;
  startTime: string;
  endTime: string;
  isBooked: boolean;
}
export interface Appointment {
  id: string;
  uuid?: string;
  patientId: string;
  doctorId: string;
  patientName: string;
  doctorName: string;
  date: string;
  startTime: string;
  endTime: string;
  encounterId?: string;
  assessmentRequestId?: string;
  status: "confirmed" | "cancelled" | "completed";
}
export interface Schedule {
  date: string;
  startTime: string;
  endTime: string;
}
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export class StaleSession extends Error {}
const objectId = /^[a-f0-9]{24}$/;
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
function invalid(): never {
  throw new ApiError(
    503,
    "The service returned an unexpected response. Please try again.",
  );
}
function record(v: unknown): Record<string, unknown> {
  if (!v || typeof v !== "object" || Array.isArray(v)) invalid();
  return v as Record<string, unknown>;
}
function string(v: unknown, max = 120): string {
  if (typeof v !== "string" || !v || v.length > max) invalid();
  return v;
}
function id(v: unknown): string {
  const s = string(v);
  if (!objectId.test(s)) invalid();
  return s;
}
function date(v: unknown): string {
  const s = string(v);
  if (!/^\d{4}-\d{2}-\d{2}(T00:00:00\.000Z)?$/.test(s)) invalid();
  const day = s.slice(0, 10),
    parsed = Date.parse(day + "T00:00:00Z");
  if (
    !Number.isFinite(parsed) ||
    new Date(parsed).toISOString().slice(0, 10) !== day
  )
    invalid();
  return day;
}
function time(v: unknown): string {
  const s = string(v);
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(s)) invalid();
  return s;
}
function list(v: unknown): unknown[] {
  if (!Array.isArray(v) || v.length > 200) invalid();
  return v;
}
export function principal(value: unknown): Principal {
  const v = record(value);
  if (
    Object.keys(v).sort().join(",") !==
      "expiresAt,issuer,role,schemaVersion,sessionId,subject" ||
    v.schemaVersion !== 1 ||
    v.issuer !== "urn:stroke-platform:identity:v1" ||
    !["patient", "doctor", "technician", "admin"].includes(v.role as string) ||
    !uuid.test(v.sessionId as string) ||
    !Number.isInteger(v.expiresAt) ||
    (v.expiresAt as number) <= Date.now() / 1000 ||
    (v.expiresAt as number) > Date.now() / 1000 + 901
  )
    invalid();
  id(v.subject);
  return v as unknown as Principal;
}
export function message(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "Unable to complete this request. Please try again.";
}
export class ApiClient {
  #token: string | null = null;
  #epoch = 0;
  #pending = new Set<AbortController>();
  onExpired: () => void = () => {};
  constructor(private transport: typeof fetch = (...args) => fetch(...args)) {}
  clear() {
    this.#epoch++;
    this.#token = null;
    for (const c of this.#pending) c.abort();
    this.#pending.clear();
  }
  private async request(
    path: string,
    method = "GET",
    body?: unknown,
    authenticated = true,
    timeout = 10000,
    binary = false,
  ): Promise<unknown> {
    const epoch = this.#epoch,
      token = this.#token;
    if (authenticated && !token)
      throw new ApiError(401, "Please sign in again.");
    const controller = new AbortController();
    this.#pending.add(controller);
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await this.transport(path, {
        method,
        body: body === undefined ? undefined : JSON.stringify(body),
        headers: {
          Accept: "application/json",
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
          ...(authenticated ? { Authorization: `Bearer ${token}` } : {}),
        },
        signal: controller.signal,
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
      });
      if (epoch !== this.#epoch) throw new StaleSession();
      if (response.status === 401 && authenticated) {
        this.clear();
        this.onExpired();
        throw new ApiError(401, "Your session ended. Sign in again.");
      }
      if (!response.ok) {
        const errors: Record<number, string> = {
          400: "Please check your details. The service did not accept this request.",
          401: "Email or password not accepted.",
          403: "Your account is not permitted to perform this action.",
          404: "This record is not available to your account.",
          409: "This record changed or is unavailable. Refresh before trying again.",
          422: "Assessment intake was rejected. Verify the explicit mappings with an operator and refresh the appointment.",
          429: "Too many requests. Please wait before trying again.",
        };
        throw new ApiError(
          response.status,
          errors[response.status] ||
            "The scheduling service is unavailable. Please try again shortly.",
        );
      }
      if (binary) {
        if (response.headers.get("content-type") !== "image/png") invalid();
        const blob = await response.blob();
        if (epoch !== this.#epoch) throw new StaleSession();
        if (!blob.size || blob.size > 1048576) invalid();
        return blob;
      }
      if (response.status === 204) return null;
      if (!response.headers.get("content-type")?.includes("application/json"))
        invalid();
      const value: unknown = await response.json();
      if (epoch !== this.#epoch) throw new StaleSession();
      return value;
    } catch (e) {
      if (epoch !== this.#epoch && !(e instanceof ApiError && e.status === 401))
        throw new StaleSession();
      if (e instanceof ApiError || e instanceof StaleSession) throw e;
      throw new ApiError(
        503,
        method === "GET"
          ? "Unable to reach the scheduling service. Try refreshing."
          : "The response could not be confirmed. Refresh your records before retrying this action.",
      );
    } finally {
      clearTimeout(timer);
      this.#pending.delete(controller);
    }
  }
  async authenticate(
    mode: "login" | "register",
    data: { email: string; password: string; name?: string },
  ): Promise<Principal> {
    this.clear();
    const generation = this.#epoch;
    const result = record(
      await this.request(`/api/v1/identity/auth/${mode}`, "POST", data, false),
    );
    const token = string(result.token, 4096);
    this.#token = token;
    try {
      return await this.me();
    } catch (e) {
      if (generation === this.#epoch) this.clear();
      throw e;
    }
  }
  async me() {
    return principal(await this.request("/api/v1/identity/me"));
  }
  async logout(all = false): Promise<void> {
    const token = this.#token;
    this.clear();
    if (!token) return;
    const controller = new AbortController(),
      timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await this.transport(
        `/api/v1/identity/auth/${all ? "logout-all" : "logout"}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
          credentials: "omit",
          redirect: "error",
          signal: controller.signal,
        },
      );
      if (!response.ok && response.status !== 401) throw new Error();
    } catch {
      throw new ApiError(
        503,
        "Signed out on this device. Server revocation could not be confirmed; the session will expire within 15 minutes.",
      );
    } finally {
      clearTimeout(timer);
    }
  }
  async slots(doctorId?: string): Promise<Slot[]> {
    const result = record(
      await this.request(
        "/api/availability?" +
          (doctorId
            ? `doctorId=${encodeURIComponent(doctorId)}`
            : "availableOnly=true"),
      ),
    );
    return list(result.availability).map((value) => {
      const v = record(value);
      const doctor = id(v.doctorId);
      if ((doctorId && doctor !== doctorId) || typeof v.isBooked !== "boolean")
        invalid();
      return {
        id: id(v._id),
        doctorId: doctor,
        doctorName: string(v.doctorName),
        date: date(v.date),
        startTime: time(v.startTime),
        endTime: time(v.endTime),
        isBooked: v.isBooked,
      };
    });
  }
  async appointments(owner: Principal, status = ""): Promise<Appointment[]> {
    const result = record(
      await this.request(
        "/api/appointments" +
          (status ? `?status=${encodeURIComponent(status)}` : ""),
      ),
    );
    return list(result.appointments).map((value) => {
      const v = record(value);
      const patientId = id(v.patientId),
        doctorId = id(v.doctorId);
      if (
        (owner.role === "patient"
          ? patientId
          : owner.role === "doctor"
            ? doctorId
            : "") !== owner.subject ||
        !["confirmed", "cancelled", "completed"].includes(v.status as string)
      )
        invalid();
      if (
        v.appointmentUuid !== undefined &&
        !uuid.test(v.appointmentUuid as string)
      )
        invalid();
      return {
        id: id(v._id),
        uuid: v.appointmentUuid as string | undefined,
        patientId,
        doctorId,
        patientName: string(v.patientName),
        doctorName: string(v.doctorName),
        date: date(v.date),
        startTime: time(v.startTime),
        endTime: time(v.endTime),
        encounterId:
          typeof v.encounterId === "string" && uuid.test(v.encounterId)
            ? v.encounterId
            : undefined,
        assessmentRequestId:
          typeof v.assessmentRequestId === "string" &&
          uuid.test(v.assessmentRequestId)
            ? v.assessmentRequestId
            : undefined,
        status: v.status as Appointment["status"],
      };
    });
  }
  async book(slot: string) {
    await this.request("/api/v1/appointments", "POST", {
      schemaVersion: 1,
      availabilityId: slot,
    });
  }
  async cancel(item: Appointment) {
    await this.request(
      item.uuid
        ? `/api/v1/appointments/${item.uuid}/cancel`
        : `/api/appointments/${item.id}/cancel`,
      "PATCH",
      item.uuid ? { schemaVersion: 1 } : {},
    );
  }
  async publish(schedule: Schedule, slot?: string) {
    await this.request(
      slot ? `/api/availability/${slot}` : "/api/availability",
      slot ? "PUT" : "POST",
      schedule,
    );
  }
  async remove(slot: string) {
    await this.request(`/api/availability/${slot}`, "DELETE");
  }
  async sessions(): Promise<number> {
    const v = record(await this.request("/api/v1/identity/sessions"));
    if (
      v.schemaVersion !== 1 ||
      !Array.isArray(v.sessions) ||
      v.sessions.length > 100
    )
      invalid();
    return v.sessions.length;
  }
  async clinical(path: string, method = "GET", body?: unknown) {
    return this.request("/api/v1/clinical/" + path, method, body, true, 35000);
  }
  async startAssessment(appointment: string, command: unknown) {
    return this.request(
      `/api/v1/appointments/${appointment}/assessment-requests`,
      "POST",
      command,
    );
  }
  async scan(encounter: string, scan: string): Promise<Blob> {
    return (await this.request(
      `/api/v1/clinical/encounters/${encounter}/scans/${scan}`,
      "GET",
      undefined,
      true,
      10000,
      true,
    )) as Blob;
  }
  async identity(path: string, method = "GET", body?: unknown) {
    return this.request("/api/v1/identity/" + path, method, body);
  }
  async recover(body: unknown, reset = false) {
    return this.request(
      "/api/v1/identity/auth/password-recovery/" +
        (reset ? "reset" : "request"),
      "POST",
      body,
      false,
    );
  }
}

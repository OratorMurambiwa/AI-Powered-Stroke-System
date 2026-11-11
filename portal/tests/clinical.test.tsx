import { it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiClient, type Principal } from "../src/api";
import { Clinical, assessment } from "../src/Clinical";
import { Admin, Recovery } from "../src/Admin";
const encounter = "11111111-1111-4111-8111-111111111111";
const patient = "22222222-2222-4222-8222-222222222222";
const principal = (role = "patient") =>
  ({
    schemaVersion: 1,
    issuer: "urn:stroke-platform:identity:v1",
    subject: "a".repeat(24),
    role,
    sessionId: encounter,
    expiresAt: Math.floor(Date.now() / 1000) + 300,
  }) as Principal;
const response = (body: unknown, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
function view(state = "APPROVED") {
  return {
    schemaVersion: 1,
    encounterId: encounter,
    version: 1,
    state,
    summary: "Synthetic independent human findings",
    reviewedAt: "2026-11-10T00:00:00Z",
    reviewedBy: "a".repeat(24),
    ...(state === "APPROVED" ? {} : { history: [] }),
    experimental: true,
    inferencePerformed: false,
    clinicianReviewRequired: true,
    observations: {
      vitals: { pulseBpm: 70 },
      nihss: { gaze: 0 },
      observedAt: "2026-11-10T00:00:00Z",
      scans: [],
    },
  };
}
async function fixture(
  role = "patient",
  handler?: (path: string, options: RequestInit) => Promise<Response>,
) {
  const fetch = vi.fn(async (path: string, options: RequestInit) =>
    path.endsWith("/auth/login")
      ? response({ token: "synthetic-token" })
      : path.endsWith("/me")
        ? response(principal(role))
        : handler
          ? handler(path, options)
          : path.endsWith("/workspace")
            ? response({
                schemaVersion: 1,
                sourceId: patient,
                encounters: [
                  {
                    encounterId: encounter,
                    patientId: patient,
                    state: role === "patient" ? "APPROVED" : "DRAFT",
                    version: 1,
                  },
                ],
              })
            : path.endsWith("/predictions")
              ? response({
                  schemaVersion: 1,
                  encounterId: encounter,
                  patientVisible: false,
                  predictions: [],
                })
              : response(view(role === "patient" ? "APPROVED" : "DRAFT")),
  );
  const api = new ApiClient(fetch as typeof window.fetch);
  await api.authenticate("login", {
    email: "synthetic@example.test",
    password: "synthetic-password",
  });
  return { api, fetch };
}
it("patient projection rejects drafts, internal notes and history", () => {
  expect(() => assessment(view("SUBMITTED"), true)).toThrow();
  expect(() => assessment({ ...view(), history: [] }, true)).toThrow();
  expect(() =>
    assessment(
      { ...view(), observations: { ...view().observations, notes: [] } },
      true,
    ),
  ).toThrow();
  expect(assessment(view(), true).state).toBe("APPROVED");
});
it("patient renders approved findings and never requests predictions", async () => {
  const { api, fetch } = await fixture();
  render(<Clinical api={api} person={principal()} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Open assessment" }),
  );
  expect(
    await screen.findByRole("heading", { name: "Clinician-approved summary" }),
  ).toBeVisible();
  expect(
    screen.queryByText("Experimental AI predictions"),
  ).not.toBeInTheDocument();
  expect(fetch.mock.calls.some(([p]) => p.includes("predictions"))).toBe(false);
});
it("technicians see capture fields but no doctor notes, approval or predictions", async () => {
  const { api, fetch } = await fixture("technician");
  render(<Clinical api={api} person={principal("technician")} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Open assessment" }),
  );
  expect(await screen.findByLabelText("NIHSS gaze")).toBeRequired();
  expect(
    screen.queryByRole("button", { name: "Approve assessment" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Add clinical note" }),
  ).not.toBeInTheDocument();
  expect(fetch.mock.calls.some(([p]) => p.includes("predictions"))).toBe(false);
});
it("failed clinical command retry preserves key and expected revision", async () => {
  let posts = 0;
  const bodies: unknown[] = [];
  const { api } = await fixture("technician", async (p, options) => {
    if (options.method === "POST") {
      bodies.push(JSON.parse(String(options.body)));
      return ++posts === 1
        ? response({}, 503)
        : response({ schemaVersion: 1, state: "DRAFT", version: 2 });
    }
    return p.endsWith("/workspace")
      ? response({
          schemaVersion: 1,
          encounters: [
            {
              encounterId: encounter,
              patientId: patient,
              state: "DRAFT",
              version: 1,
            },
          ],
        })
      : response(view("DRAFT"));
  });
  render(<Clinical api={api} person={principal("technician")} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Open assessment" }),
  );
  await screen.findByLabelText("NIHSS gaze");
  fireEvent.change(screen.getByLabelText("Observed at (UTC)"), {
    target: { value: "2026-11-10T00:00" },
  });
  for (const [label, n] of [
    ["Systolic BP (mmHg)", "120"],
    ["Diastolic BP (mmHg)", "80"],
    ["Pulse (bpm)", "70"],
    ["Temperature (°C)", "37"],
    ["Oxygen saturation (%)", "98"],
    ["Glucose (mg/dL)", "90"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value: n } });
  for (const key of [
    "consciousness",
    "questions",
    "commands",
    "gaze",
    "visual",
    "facial",
    "leftArm",
    "rightArm",
    "leftLeg",
    "rightLeg",
    "ataxia",
    "sensory",
    "language",
    "dysarthria",
    "neglect",
  ])
    fireEvent.change(screen.getByLabelText("NIHSS " + key), {
      target: { value: "0" },
    });
  await userEvent.click(
    screen.getByRole("button", { name: "Record observations" }),
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Retry pending action" }),
  );
  expect(await screen.findByText("Clinical action recorded.")).toBeVisible();
  expect(bodies).toHaveLength(2);
  expect(bodies[0]).toEqual(bodies[1]);
});
it("admin provision uses password recheck without returning an activation secret", async () => {
  let sent: unknown;
  const { api } = await fixture("admin", async (path, options) => {
    if (options.method === "POST") {
      sent = JSON.parse(String(options.body));
      return response({
        schemaVersion: 1,
        user: { id: "b".repeat(24), role: "doctor", state: "invited" },
        deliveryId: encounter,
      });
    }
    return response({ schemaVersion: 1, staff: [] });
  });
  render(<Admin api={api} person={principal("admin")} />);
  for (const [label, value] of [
    ["Staff name", "Synthetic clinician"],
    ["Staff email", "new@example.test"],
    ["Your current password", "Synthetic-private-password"],
    ["Authorization reason", "Synthetic verified onboarding"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  await userEvent.click(
    screen.getByRole("button", { name: "Invite staff member" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Awaiting activation",
  );
  expect(sent).toMatchObject({
    role: "doctor",
    currentPassword: "Synthetic-private-password",
  });
  expect(screen.getByLabelText("Your current password")).toHaveValue("");
});
it("recovery stays generic and uses the original public recovery contract", async () => {
  const fetch = vi.fn(async (_path: string, _options?: RequestInit) =>
    response({ message: "generic" }, 202),
  );
  const api = new ApiClient(fetch as typeof window.fetch);
  render(<Recovery api={api} />);
  fireEvent.change(screen.getByLabelText("Registered email"), {
    target: { value: "unknown@example.test" },
  });
  await userEvent.click(
    screen.getByRole("button", { name: "Request recovery instructions" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "If recovery is available",
  );
  expect(fetch.mock.calls[0][0]).toBe(
    "/api/v1/identity/auth/password-recovery/request",
  );
  expect(localStorage.length + sessionStorage.length).toBe(0);
});

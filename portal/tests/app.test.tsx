import { it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../src/App";
import { ApiClient } from "../src/api";
const me = (role = "patient") => ({
  schemaVersion: 1,
  issuer: "urn:stroke-platform:identity:v1",
  subject: "a".repeat(24),
  role,
  sessionId: "11111111-1111-4111-8111-111111111111",
  expiresAt: Math.floor(Date.now() / 1000) + 300,
});
const res = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
function fixture(role = "patient") {
  const fetch = vi.fn(async (path: string) =>
    path.endsWith("/login")
      ? res({ token: "synthetic-token" })
      : path.endsWith("/me")
        ? res(me(role))
        : path.includes("/availability")
          ? res({ availability: [] })
          : path.endsWith("/workspace")
            ? res({
                schemaVersion: 1,
                sourceId: "11111111-1111-4111-8111-111111111111",
                encounters: [],
                limit: 100,
              })
            : path.includes("/sessions")
              ? res({ schemaVersion: 1, sessions: [] })
              : res({ appointments: [] }),
  );
  const api = new ApiClient(fetch as typeof window.fetch);
  return { fetch, api };
}
async function signIn() {
  const user = userEvent.setup();
  await user.type(
    screen.getByLabelText("Email address"),
    "synthetic@example.test",
  );
  await user.type(screen.getByLabelText("Password"), "Synthetic-password");
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  return user;
}
it("signs in and displays real empty data states with accessible navigation", async () => {
  const { api } = fixture();
  render(<App client={api} />);
  await signIn();
  expect(await screen.findByText("No appointments here yet")).toBeVisible();
  expect(
    screen.getByRole("navigation", { name: "Main navigation" }),
  ).toBeVisible();
  expect(screen.getByText("No published times available")).toBeVisible();
});
it("registration has no staff role selector and requires patient details", async () => {
  history.replaceState(null, "", "/register");
  const { api } = fixture();
  render(<App client={api} />);
  expect(
    screen.getByRole("button", { name: "Create patient account" }),
  ).toBeVisible();
  expect(screen.getByLabelText("Full name")).toBeRequired();
  expect(screen.getByLabelText("Password")).toHaveAttribute("minlength", "12");
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
});
it("doctor-only pages are forbidden without exposing schedule controls", async () => {
  const { api } = fixture();
  render(<App client={api} />);
  await signIn();
  await screen.findByText("No appointments here yet");
  history.pushState(null, "", "/doctor");
  window.dispatchEvent(new PopStateEvent("popstate"));
  expect(
    await screen.findByText("This workspace is not available to your account."),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Publish availability" }),
  ).not.toBeInTheDocument();
});
it("technicians do not fetch appointment or clinical data", async () => {
  const { api, fetch } = fixture("technician");
  render(<App client={api} />);
  await signIn();
  expect(
    await screen.findByRole("heading", {
      name: "Assigned assessment workspace",
    }),
  ).toBeVisible();
  expect(
    fetch.mock.calls.some(
      ([p]) => p.includes("/appointments") || p.includes("/predictions"),
    ),
  ).toBe(false);
});
it("a live expired session removes protected content", async () => {
  const { api } = fixture();
  render(<App client={api} />);
  await signIn();
  await screen.findByText("No appointments here yet");
  api.clear();
  api.onExpired();
  expect(await screen.findByRole("button", { name: "Sign in" })).toBeVisible();
  expect(
    screen.queryByRole("heading", { name: "My appointments" }),
  ).not.toBeInTheDocument();
});
it("service unavailability is visible and refresh can recover", async () => {
  const { api, fetch } = fixture();
  fetch.mockImplementation(async (path: string) =>
    path.endsWith("/login")
      ? res({ token: "synthetic-token" })
      : path.endsWith("/me")
        ? res(me())
        : res({}, 503),
  );
  render(<App client={api} />);
  const user = await signIn();
  expect(await screen.findByRole("alert")).toHaveTextContent("unavailable");
  fetch.mockImplementation(async (path: string) =>
    path.includes("/availability")
      ? res({ availability: [] })
      : res({ appointments: [] }),
  );
  await user.click(screen.getByRole("button", { name: "Refresh records" }));
  expect(await screen.findByText("No appointments here yet")).toBeVisible();
});
it("untrusted doctor names render as text and booking refreshes only after response", async () => {
  const { api, fetch } = fixture();
  const slot = {
    _id: "b".repeat(24),
    doctorId: "c".repeat(24),
    doctorName: "<img src=x onerror=alert(1)>",
    date: "2099-01-02T00:00:00.000Z",
    startTime: "10:00",
    endTime: "11:00",
    isBooked: false,
  };
  fetch.mockImplementation(async (path: string) =>
    path.endsWith("/login")
      ? res({ token: "synthetic-token" })
      : path.endsWith("/me")
        ? res(me())
        : path.includes("/availability")
          ? res({ availability: [slot] })
          : res({ appointments: [] }),
  );
  render(<App client={api} />);
  const user = await signIn();
  expect(await screen.findByText(slot.doctorName)).toBeVisible();
  expect(document.querySelector("img")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Book appointment" }));
  await waitFor(() =>
    expect(fetch.mock.calls.some(([p]) => p === "/api/v1/appointments")).toBe(
      true,
    ),
  );
  expect(await screen.findByText("Appointment booked.")).toBeVisible();
});

import { describe, it, expect, vi } from "vitest";
import { ApiClient, StaleSession, principal } from "../src/api";
const p = () => ({
  schemaVersion: 1,
  issuer: "urn:stroke-platform:identity:v1",
  subject: "a".repeat(24),
  role: "patient",
  sessionId: "11111111-1111-4111-8111-111111111111",
  expiresAt: Math.floor(Date.now() / 1000) + 300,
});
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
const login = (transport: ReturnType<typeof vi.fn>) => {
  transport
    .mockResolvedValueOnce(
      response({ token: "synthetic-memory-token", user: { role: "admin" } }),
    )
    .mockResolvedValueOnce(response(p()));
};
describe("memory-only authority adapter", () => {
  it("uses live me role, omits registration roles and storage", async () => {
    const fetch = vi.fn();
    login(fetch);
    const client = new ApiClient(fetch);
    expect(
      (
        await client.authenticate("register", {
          email: "a@example.test",
          password: "synthetic-password",
          name: "Synthetic",
        })
      ).role,
    ).toBe("patient");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).not.toHaveProperty("role");
    expect(fetch.mock.calls[1][1].headers.Authorization).toBe(
      "Bearer synthetic-memory-token",
    );
    expect(localStorage.length + sessionStorage.length).toBe(0);
  });
  it("invalidates memory and notifies on a live 401", async () => {
    const fetch = vi.fn();
    login(fetch);
    const client = new ApiClient(fetch);
    await client.authenticate("login", {
      email: "a@example.test",
      password: "synthetic-password",
    });
    client.onExpired = vi.fn();
    fetch.mockResolvedValueOnce(response({}, 401));
    await expect(client.me()).rejects.toMatchObject({ status: 401 });
    expect(client.onExpired).toHaveBeenCalledOnce();
    await expect(client.me()).rejects.toMatchObject({ status: 401 });
    expect(fetch).toHaveBeenCalledTimes(3);
  });
  it("rejects stale protected responses after clear", async () => {
    const fetch = vi.fn();
    login(fetch);
    const client = new ApiClient(fetch);
    await client.authenticate("login", {
      email: "a@example.test",
      password: "synthetic-password",
    });
    let finish!: (v: Response) => void;
    fetch.mockImplementationOnce(() => new Promise((r) => (finish = r)));
    const pending = client.me();
    client.clear();
    finish(response(p()));
    await expect(pending).rejects.toBeInstanceOf(StaleSession);
  });
  it("rejects wrong-owner data rather than rendering it", async () => {
    const fetch = vi.fn();
    login(fetch);
    const client = new ApiClient(fetch);
    const owner = await client.authenticate("login", {
      email: "a@example.test",
      password: "synthetic-password",
    });
    fetch.mockResolvedValueOnce(
      response({
        appointments: [
          {
            patientId: "b".repeat(24),
            doctorId: "c".repeat(24),
            status: "confirmed",
          },
        ],
      }),
    );
    await expect(client.appointments(owner)).rejects.toMatchObject({
      status: 503,
    });
  });
  it("surfaces conflicts and ambiguous transport failures without retry", async () => {
    const fetch = vi.fn();
    login(fetch);
    const client = new ApiClient(fetch);
    await client.authenticate("login", {
      email: "a@example.test",
      password: "synthetic-password",
    });
    fetch.mockResolvedValueOnce(response({}, 409));
    await expect(client.book("a".repeat(24))).rejects.toMatchObject({
      status: 409,
    });
    fetch.mockRejectedValueOnce(new TypeError("offline"));
    await expect(client.book("a".repeat(24))).rejects.toThrow(
      "Refresh your records",
    );
    expect(fetch).toHaveBeenCalledTimes(4);
  });
  it("clears local access even when server logout fails", async () => {
    const fetch = vi.fn();
    login(fetch);
    const client = new ApiClient(fetch);
    await client.authenticate("login", {
      email: "a@example.test",
      password: "synthetic-password",
    });
    fetch.mockRejectedValueOnce(new TypeError("offline"));
    await expect(client.logout()).rejects.toThrow(
      "Server revocation could not be confirmed",
    );
    await expect(client.me()).rejects.toMatchObject({ status: 401 });
  });
  it("rejects invalid calendar dates in scheduling responses", async () => {
    const fetch = vi.fn();
    login(fetch);
    const client = new ApiClient(fetch);
    await client.authenticate("login", {
      email: "a@example.test",
      password: "synthetic-password",
    });
    fetch.mockResolvedValueOnce(
      response({
        availability: [
          {
            _id: "b".repeat(24),
            doctorId: "c".repeat(24),
            doctorName: "Synthetic doctor",
            date: "2026-02-31",
            startTime: "09:00",
            endTime: "10:00",
            isBooked: false,
          },
        ],
      }),
    );
    await expect(client.slots()).rejects.toMatchObject({ status: 503 });
  });
  it("an older login cannot erase a newer successfully verified session", async () => {
    let finish!: (v: Response) => void;
    const fetch = vi.fn();
    fetch
      .mockResolvedValueOnce(response({ token: "synthetic-first" }))
      .mockImplementationOnce(() => new Promise((r) => (finish = r)));
    const client = new ApiClient(fetch);
    const first = client.authenticate("login", {
      email: "first@example.test",
      password: "synthetic-password",
    });
    const rejected = expect(first).rejects.toBeInstanceOf(StaleSession);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    const second = { ...p(), subject: "b".repeat(24) };
    fetch
      .mockResolvedValueOnce(response({ token: "synthetic-second" }))
      .mockResolvedValueOnce(response(second));
    expect(
      (
        await client.authenticate("login", {
          email: "second@example.test",
          password: "synthetic-password",
        })
      ).subject,
    ).toBe(second.subject);
    finish(response(p()));
    await rejected;
    fetch.mockResolvedValueOnce(response(second));
    expect((await client.me()).subject).toBe(second.subject);
  });
  it("rejects malformed, expired and unsupported identity contracts", () => {
    for (const changes of [
      { role: "physician" },
      { schemaVersion: 2 },
      { expiresAt: 0 },
      { subject: "email@example.test" },
      { extra: true },
    ])
      expect(() => principal({ ...p(), ...changes })).toThrow();
  });
});

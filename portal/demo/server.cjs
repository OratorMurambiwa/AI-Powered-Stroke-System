// Synthetic fixture and same-origin static gateway only; never a production bootstrap.
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const crypto = require("node:crypto");
if (
  process.env.MONGODB_URI !==
    "mongodb://stroke-portal-mongo:27017/synthetic_portal_demo?replicaSet=rs0" ||
  process.env.PORTAL_SYNTHETIC_DEMO !== "true"
)
  throw Error("Explicit isolated synthetic fixture required");
process.env.JWT_SECRET = crypto.randomBytes(48).toString("hex");
process.env.IDENTITY_DELIVERY_KEY = crypto.randomBytes(32).toString("hex");
process.env.NODE_ENV = "test";
process.env.RATE_LIMIT_MAX_REQUESTS = "10000";
const app = require("../../booking-backend/dist/app").default;
const { User } = require("../../booking-backend/dist/models/User");
const {
  IdentitySession,
} = require("../../booking-backend/dist/models/Identity");
const { connectDB } = require("../../booking-backend/dist/config/database");
const privateDir = "/demo-private";
let api;
let apiPort;
async function listen() {
  api = app.listen(apiPort || 0, "127.0.0.1");
  await new Promise((r) => api.once("listening", r));
  apiPort = api.address().port;
}
(async () => {
  await connectDB();
  if (await User.countDocuments())
    throw Error("Fixture refuses nonempty database");
  await listen();
  const users = {};
  for (const [name, role] of [
    ["patient", "patient"],
    ["otherPatient", "patient"],
    ["doctor", "doctor"],
    ["technician", "technician"],
    ["admin", "admin"],
  ]) {
    const password = "Synthetic-" + crypto.randomBytes(24).toString("hex");
    const user = await User.create({
      name: "Synthetic " + (role === "doctor" ? "Dr Rivera" : name),
      email: name.toLowerCase() + "@example.test",
      password,
      role,
      state: "active",
    });
    users[name] = { email: user.email, password, id: String(user._id) };
  }
  const auth = await fetch(
    `http://127.0.0.1:${apiPort}/api/v1/identity/auth/login`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(users.doctor, ["email", "password"]),
    },
  );
  const session = await auth.json();
  if (!auth.ok) throw Error("Fixture sign-in failed");
  const date = new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 10);
  for (const [startTime, endTime] of [
    ["09:00", "09:30"],
    ["10:00", "10:30"],
  ]) {
    const response = await fetch(
      `http://127.0.0.1:${apiPort}/api/availability`,
      {
        method: "POST",
        headers: {
          Authorization: "Bearer " + session.token,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ date, startTime, endTime }),
      },
    );
    if (!response.ok) throw Error("Fixture schedule failed");
  }
  await fetch(`http://127.0.0.1:${apiPort}/api/v1/identity/auth/logout`, {
    method: "POST",
    headers: { Authorization: "Bearer " + session.token },
  });
  fs.writeFileSync(
    path.join(privateDir, "credentials.json"),
    JSON.stringify({ users, date }),
    { mode: 0o600 },
  );
  const root = path.resolve(__dirname, "../dist");
  const gateway = http.createServer((req, res) => {
    const headers = {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "Content-Security-Policy":
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    };
    if (req.url.startsWith("/api/")) {
      const upstream = http.request(
        {
          hostname: "127.0.0.1",
          port: apiPort,
          path: req.url,
          method: req.method,
          headers: { ...req.headers, host: "127.0.0.1:" + apiPort },
        },
        (reply) => {
          res.writeHead(reply.statusCode, { ...reply.headers, ...headers });
          reply.pipe(res);
        },
      );
      upstream.setTimeout(10000, () => upstream.destroy());
      upstream.on("error", () => {
        if (!res.headersSent)
          res.writeHead(503, {
            "Content-Type": "application/json",
            ...headers,
          });
        res.end('{"error":"service_unavailable"}');
      });
      req.pipe(upstream);
      return;
    }
    if (!["GET", "HEAD"].includes(req.method)) {
      res.writeHead(405, headers);
      res.end();
      return;
    }
    let pathname;
    try {
      pathname = decodeURIComponent(new URL(req.url, "http://local").pathname);
    } catch {
      res.writeHead(400, headers);
      res.end();
      return;
    }
    const candidate = path.resolve(root, "." + pathname);
    if (candidate !== root && !candidate.startsWith(root + path.sep)) {
      res.writeHead(404, headers);
      res.end();
      return;
    }
    const file = pathname.startsWith("/assets/")
      ? candidate
      : path.join(root, "index.html");
    if (!fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404, headers);
      res.end();
      return;
    }
    const types = {
      ".html": "text/html; charset=utf-8",
      ".js": "text/javascript; charset=utf-8",
      ".css": "text/css; charset=utf-8",
    };
    res.writeHead(200, {
      "Content-Type": types[path.extname(file)] || "application/octet-stream",
      ...headers,
    });
    if (req.method === "HEAD") res.end();
    else fs.createReadStream(file).pipe(res);
  });
  gateway.listen(4173, "0.0.0.0");
  // Test control is a private local file, never an HTTP route or runtime endpoint.
  let controlling = false;
  setInterval(async () => {
    const file = path.join(privateDir, "control.json");
    if (controlling || !fs.existsSync(file)) return;
    controlling = true;
    try {
      const command = JSON.parse(fs.readFileSync(file));
      fs.unlinkSync(file);
      if (command.action === "expire")
        await IdentitySession.updateMany(
          { revokedAt: null },
          { $set: { expiresAt: new Date(Date.now() - 1000) } },
        );
      else if (command.action === "pause")
        await new Promise((r) => api.close(r));
      else if (command.action === "resume") await listen();
      else throw Error("Unknown private fixture control");
      fs.writeFileSync(
        path.join(privateDir, "control-ack.json"),
        JSON.stringify({ id: command.id }),
        { mode: 0o600 },
      );
    } finally {
      controlling = false;
    }
  }, 150).unref();
})().catch(() => {
  console.error("Synthetic portal fixture startup failed");
  process.exit(1);
});

// Test-only authority. Synthetic keys stay in this process; Python never receives them.
const crypto = require('node:crypto');
const readline = require('node:readline');
const { once } = require('node:events');
if (!/^mongodb:\/\/stroke-booking-mongo:27017\/(?:synthetic_clinical_identity|synthetic_workflow_identity|synthetic_assessment_review)\?replicaSet=rs0$/.test(process.env.MONGODB_URI || '')) throw new Error('Synthetic-only authority fixture');
process.env.JWT_SECRET = crypto.randomBytes(48).toString('hex');
process.env.IDENTITY_DELIVERY_KEY = crypto.randomBytes(32).toString('hex');
process.env.NODE_ENV = 'test';
process.env.RATE_LIMIT_MAX_REQUESTS = '10000';
const app = require('../dist/app').default;
const { User } = require('../dist/models/User');
const { connectDB, disconnectDB } = require('../dist/config/database');
const { IdentitySession } = require('../dist/models/Identity');
let server;
async function listen(port = 0) {
  server = app.listen(port, '127.0.0.1');
  await once(server, 'listening');
  return server.address().port;
}
(async () => {
  await connectDB();
  let port = await listen();
  const password = 'Synthetic-' + crypto.randomBytes(20).toString('hex');
  const users = {};
  for (const [name, role] of [['patientA', 'patient'], ['patientB', 'patient'], ['unmapped', 'patient'], ['doctor', 'doctor'], ['otherDoctor', 'doctor'], ['technician', 'technician'], ['otherTech', 'technician'], ['admin', 'admin']]) {
    const user = await User.create({ email: `${name.toLowerCase()}@example.test`, name: 'Synthetic fixture', role, password });
    const result = await fetch(`http://127.0.0.1:${port}/api/v1/identity/auth/login`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ email: user.email, password }) });
    if (result.status !== 200) throw new Error('Synthetic fixture login failed');
    const body = await result.json();
    users[name] = { ...body.user, token: body.token, password };
  }
  // Private child-process pipe only, never a file, HTTP fixture endpoint or application log.
  process.stdout.write(JSON.stringify({ port, users }) + '\n');
  const input = readline.createInterface({ input: process.stdin });
  for await (const line of input) {
    const command = JSON.parse(line);
    if (command.action === 'pause') {
      await new Promise(resolve => server.close(resolve));
      process.stdout.write('{"status":"paused"}\n');
    } else if (command.action === 'resume') {
      await listen(port);
      process.stdout.write('{"status":"ready"}\n');
    } else if (command.action === 'expire') {
      // Explicit fixture-only stored-session expiration, never a runtime endpoint.
      const jwt = require('jsonwebtoken');
      await IdentitySession.updateOne({ _id: jwt.decode(users[command.user].token).sid }, { $set: { expiresAt: new Date(Date.now() - 1000) } });
      process.stdout.write('{"status":"expired"}\n');
    } else if (command.action === 'resetLimits') {
      const limits = require('../dist/middleware/rateLimiter');
      for (const limiter of Object.values(limits)) for (const key of ['127.0.0.1','::ffff:127.0.0.1','::/56']) limiter.resetKey(key);
      process.stdout.write('{"status":"reset"}\n');
    } else if (command.action === 'clinicalUrl') {
      require('../dist/config').config.clinicalApiUrl = command.url;
      process.stdout.write('{"status":"configured"}\n');
    } else if (command.action === 'inspectWorkflow') {
      const { AssessmentRequest } = require('../dist/models/AssessmentRequest');
      const { Appointment } = require('../dist/models/Appointment');
      const record = await AssessmentRequest.findById(command.requestId).lean();
      process.stdout.write(JSON.stringify({ state: record?.state ?? null, attempts: record?.attempts ?? 0, blocking: record?.blocking ?? null,
        reservations: await Appointment.countDocuments({ assessmentRequestId: command.requestId }) }) + '\n');
    } else if (command.action === 'expireLease') {
      await require('../dist/models/AssessmentRequest').AssessmentRequest.updateOne({ _id: command.requestId }, { $set: { leaseUntil: new Date(0) } });
      process.stdout.write('{"status":"lease_expired"}\n');
    } else if (command.action === 'appointmentStatus') {
      await require('../dist/models/Appointment').Appointment.updateOne({ appointmentUuid: command.appointmentId }, { $set: { status: command.status } });
      process.stdout.write('{"status":"fixture_updated"}\n');
    } else if (command.action === 'failFinalize') {
      // One-shot test-only seam around Mongo acknowledgement, not a runtime option.
      const { AssessmentRequest } = require('../dist/models/AssessmentRequest');
      if (command.kind === 'appointment') {
        const { Appointment } = require('../dist/models/Appointment');
        const original = Appointment.updateOne;
        Appointment.updateOne = function (filter, update, options) {
          if (update?.$set?.encounterId) { Appointment.updateOne = original; return Promise.resolve({ matchedCount: 0 }); }
          return original.call(this, filter, update, options);
        };
      } else {
        const original = AssessmentRequest.findOneAndUpdate;
        AssessmentRequest.findOneAndUpdate = function (filter, update, options) {
          if (update?.$set?.state === 'CREATED') { AssessmentRequest.findOneAndUpdate = original; throw new Error('Synthetic acknowledgement failure'); }
          return original.call(this, filter, update, options);
        };
      }
      process.stdout.write('{"status":"armed"}\n');
    } else if (command.action === 'stop') break;
    else throw new Error('Unknown synthetic fixture command');
  }
  if (server.listening) await new Promise(resolve => server.close(resolve));
  await disconnectDB();
})().catch(() => { process.stderr.write('Synthetic authority fixture failed\n'); process.exit(1); });

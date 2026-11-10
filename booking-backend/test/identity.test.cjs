const { test, before, after, beforeEach } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const jwt = require('jsonwebtoken');
const request = require('supertest');
const mongoose = require('mongoose');
if (!/^mongodb:\/\/stroke-booking-mongo:27017\/synthetic_booking_test\?replicaSet=rs0$/.test(process.env.TEST_MONGODB_URI || '')) throw new Error('Private synthetic replica set required');
process.env.NODE_ENV = 'test';
process.env.JWT_SECRET = crypto.randomBytes(48).toString('hex');
process.env.IDENTITY_DELIVERY_KEY = crypto.randomBytes(32).toString('hex');
process.env.MONGODB_URI = process.env.TEST_MONGODB_URI.replace('synthetic_booking_test', 'synthetic_identity_test');
process.env.RATE_LIMIT_MAX_REQUESTS = '1000';
const app = require('../dist/app').default;
const { config } = require('../dist/config');
const { connectDB, disconnectDB } = require('../dist/config/database');
const { User } = require('../dist/models/User');
const { IdentitySession, IdentityAudit, IdentityDelivery, IdentityChallenge, IdentityControl } = require('../dist/models/Identity');
const { bootstrapAdmin, consumeDelivery, authenticateToken, tokenHash } = require('../dist/services/identity.service');
const { authLimiter, recoveryLimiter, bookingLimiter } = require('../dist/middleware/rateLimiter');
const { spawnSync, spawn } = require('node:child_process');
const prefix = '/api/v1/identity';
const secret = 'Synthetic-Identity-Password!';
let admin, patient, otherPatient, doctor, technician, activation;
let sequence = 0;
function resetLimits() {
  for (const limiter of [authLimiter, recoveryLimiter, bookingLimiter]) for (const key of ['::ffff:127.0.0.1', '127.0.0.1', '::/56']) limiter.resetKey(key);
}
function api(method, path, actor) {
  const result = request(app)[method](path);
  return actor ? result.set('Authorization', `Bearer ${actor.token}`) : result;
}
async function login(email, password = secret) {
  resetLimits();
  const result = await api('post', prefix + '/auth/login').send({ email, password });
  assert.equal(result.status, 200);
  return { ...result.body.user, token: result.body.token };
}
async function register() {
  resetLimits();
  const email = `patient-${++sequence}@example.test`;
  const result = await api('post', prefix + '/auth/register').send({ email, name: 'Synthetic Patient', password: secret });
  assert.equal(result.status, 201);
  return { ...result.body.user, token: result.body.token };
}
async function provision(role = 'doctor') {
  resetLimits();
  const email = `staff-${++sequence}@example.test`;
  const response = await api('post', prefix + '/staff', admin).send({ email, name: 'Synthetic Staff', role, reason: 'SYNTHETIC authorization fixture', currentPassword: secret });
  assert.equal(response.status, 201);
  return { ...response.body.user, email, deliveryId: response.body.deliveryId };
}
async function activate(invited) {
  const delivered = await consumeDelivery(invited.deliveryId, 'synthetic-test-operator');
  resetLimits();
  assert.equal((await api('post', prefix + '/auth/password-recovery/reset').send({ token: delivered.token, newPassword: secret })).status, 204);
  return login(delivered.email);
}
async function recovery(actor) {
  resetLimits();
  await User.updateOne({ _id: actor.id }, { $unset: { recoveryRequestedAt: '' } });
  const response = await api('post', prefix + '/auth/password-recovery/request').send({ email: actor.email });
  assert.equal(response.status, 202);
  const delivery = await IdentityDelivery.findOne({ userId: actor.id, consumedAt: null });
  assert.ok(delivery);
  const payload = await consumeDelivery(delivery.id, 'synthetic-recovery-operator');
  return { response, payload, delivery };
}
async function operatorCli(mode, answers, database) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ['dist/identity/operator.js', mode], {
      cwd: require('node:path').resolve(__dirname, '..'),
      env: { ...process.env, MONGODB_URI: process.env.MONGODB_URI.replace('synthetic_identity_test', database), ALLOW_IDENTITY_BOOTSTRAP: 'true' },
    });
    let output = ''; let prompt = ''; let index = 0;
    const timer = setTimeout(() => { child.kill(); reject(new Error('Synthetic operator CLI timed out')); }, 15000);
    child.stdout.on('data', chunk => { output += chunk; });
    child.stderr.on('data', chunk => {
      prompt += chunk;
      if (prompt.endsWith(': ') && index < answers.length) { child.stdin.write(answers[index++] + '\n'); prompt = ''; }
    });
    child.on('error', reject);
    child.on('close', code => { clearTimeout(timer); resolve({ code, output }); });
  });
}
before(async () => { await connectDB(); });
after(async () => { await disconnectDB(); });
beforeEach(resetLimits);

test('shared identity authority against synthetic real MongoDB', async t => {
  await t.test('bootstrap is opt-in, one-time and serialized, never a public endpoint', async () => {
    delete process.env.ALLOW_IDENTITY_BOOTSTRAP;
    await assert.rejects(bootstrapAdmin({ email: 'bootstrap@example.test', name: 'Synthetic Admin', reason: 'SYNTHETIC initial authorization' }, 'test-operator'), e => e.status === 403);
    assert.equal(await User.countDocuments(), 0);
    process.env.ALLOW_IDENTITY_BOOTSTRAP = 'true';
    const outcomes = await Promise.allSettled(['a', 'b'].map(suffix => bootstrapAdmin({ email: `bootstrap-${suffix}@example.test`, name: 'Synthetic Admin', reason: 'SYNTHETIC initial authorization' }, 'test-operator')));
    assert.equal(outcomes.filter(r => r.status === 'fulfilled').length, 1);
    assert.equal(await User.countDocuments({ role: 'admin' }), 1);
    assert.equal((await IdentityControl.findById('staff-governance')).bootstrapComplete, true);
    activation = outcomes.find(r => r.status === 'fulfilled').value;
    assert.equal((await User.findById(activation.id)).state, 'invited');
    assert.equal((await api('post', prefix + '/bootstrap').send({})).status, 401);
    const events = await IdentityAudit.find({ action: 'ADMIN_BOOTSTRAPPED' });
    assert.equal(events.length, 1);
    assert.equal(events[0].actor, 'operator:test-operator');
  });
  await t.test('staff activation uses an encrypted one-time handoff and user-chosen password', async () => {
    const encrypted = await IdentityDelivery.findById(activation.deliveryId);
    assert.ok(encrypted.ciphertext && encrypted.iv && encrypted.tag);
    const payload = await consumeDelivery(activation.deliveryId, 'synthetic-test-operator');
    assert.equal(payload.kind, 'activation');
    assert.equal((await User.findById(activation.id)).state, 'invited');
    assert.equal((await api('post', prefix + '/auth/login').send({ email: payload.email, password: secret })).status, 401);
    await assert.rejects(consumeDelivery(activation.deliveryId, 'synthetic-test-operator'), e => e.status === 404);
    assert.equal((await IdentityDelivery.findById(activation.deliveryId)).ciphertext, undefined);
    assert.equal((await api('post', prefix + '/auth/password-recovery/reset').send({ token: payload.token, newPassword: secret })).status, 204);
    assert.equal((await api('post', prefix + '/auth/password-recovery/reset').send({ token: payload.token, newPassword: secret })).status, 400);
    admin = await login(payload.email);
    assert.equal(admin.role, 'admin');
    assert.equal(await IdentityAudit.countDocuments({ action: 'STAFF_ACTIVATED', subject: admin.id }), 1);
  });
  await t.test('public signup rejects every staff/alias role and extra identity claims', async () => {
    for (const role of ['doctor', 'physician', 'technician', 'admin', { $ne: 'patient' }]) {
      resetLimits();
      const response = await api('post', prefix + '/auth/register').send({ email: `forbidden-${++sequence}@example.test`, name: 'Synthetic', password: secret, role });
      assert.equal(response.status, 400);
    }
    assert.equal((await api('post', prefix + '/auth/register').send({ email: 'forbidden-extra@example.test', name: 'Synthetic', password: secret, state: 'active' })).status, 400);
    patient = await register(); otherPatient = await register();
    assert.equal(patient.role, 'patient');
    assert.equal((await User.findById(patient.id)).state, 'active');
  });
  await t.test('only an active admin with password recheck can provision audited staff', async () => {
    doctor = await activate(await provision('doctor'));
    technician = await activate(await provision('technician'));
    for (const actor of [undefined, patient, doctor, technician]) {
      assert.equal((await api('post', prefix + '/staff', actor).send({ email: 'denied@example.test', name: 'Synthetic', role: 'doctor', reason: 'SYNTHETIC', currentPassword: secret })).status, actor ? 403 : 401);
    }
    const event = await IdentityAudit.findOne({ subject: technician.id, action: 'STAFF_PROVISIONED' });
    assert.equal(event.actor, admin.id);
    assert.equal(event.toRole, 'technician');
    assert.equal(event.reason, 'SYNTHETIC authorization fixture');
    assert.equal((await api('post', '/api/availability', technician).send({ date: '2099-07-01', startTime: '10:00', endTime: '11:00' })).status, 403);
    for (const actor of [admin, technician]) assert.equal((await api('get', '/api/appointments', actor)).status, 403);
  });
  await t.test('provisioning validates role/reason/reauth and cannot promote an email-matched patient', async () => {
    for (const change of [{ role: 'patient' }, { role: 'root' }, { reason: '' }, { currentPassword: 'wrong' }, { password: secret }]) {
      const result = await api('post', prefix + '/staff', admin).send({ email: `invalid-${++sequence}@example.test`, name: 'Synthetic', role: 'doctor', reason: 'SYNTHETIC', currentPassword: secret, ...change });
      assert.ok([400, 401].includes(result.status));
    }
    const duplicate = await api('post', prefix + '/staff', admin).send({ email: patient.email.toUpperCase(), name: 'Synthetic', role: 'admin', reason: 'SYNTHETIC', currentPassword: secret });
    assert.equal(duplicate.status, 409);
    assert.equal((await User.findById(patient.id)).role, 'patient');
    assert.equal((await api('patch', prefix + `/staff/${patient.id}/role`, admin).send({ role: 'admin', reason: 'SYNTHETIC', currentPassword: secret })).status, 404);
  });
  await t.test('physician normalizes to doctor without rewriting existing identities', async () => {
    const invited = await provision('physician');
    assert.equal(invited.role, 'doctor');
    const legacy = await User.create({ name: 'Synthetic Legacy Physician', email: `physician-${++sequence}@example.test`, password: secret, role: 'physician' });
    const actor = await login(legacy.email);
    assert.equal(actor.role, 'doctor');
    assert.equal((await api('get', prefix + '/me', actor)).body.role, 'doctor');
    assert.equal((await User.findById(legacy.id)).role, 'physician');
    assert.equal((await api('post', '/api/availability', actor).send({ date: '2099-07-01', startTime: '10:00', endTime: '11:00' })).status, 201);
  });
  await t.test('role changes revoke sessions and do not grant technicians doctor permissions', async () => {
    const actor = await activate(await provision('doctor'));
    const response = await api('patch', prefix + `/staff/${actor.id}/role`, admin).send({ role: 'technician', reason: 'SYNTHETIC reassignment', currentPassword: secret });
    assert.equal(response.status, 200);
    assert.equal((await api('get', prefix + '/me', actor)).status, 401);
    const changed = await login(actor.email);
    assert.equal(changed.role, 'technician');
    assert.equal((await api('post', '/api/availability', changed).send({ date: '2099-07-02', startTime: '10:00', endTime: '11:00' })).status, 403);
    const audit = await IdentityAudit.findOne({ action: 'STAFF_ROLE_CHANGED', subject: actor.id });
    assert.equal(audit.fromRole, 'doctor'); assert.equal(audit.toRole, 'technician');
  });
  await t.test('staff revocation blocks every session, login and password recovery', async () => {
    const actor = await activate(await provision('technician'));
    const other = await login(actor.email);
    const { payload } = await recovery(actor);
    const response = await api('post', prefix + `/staff/${actor.id}/revoke`, admin).send({ reason: 'SYNTHETIC offboarding', currentPassword: secret });
    assert.equal(response.status, 200);
    for (const session of [actor, other]) assert.equal((await api('get', prefix + '/me', session)).status, 401);
    resetLimits();
    assert.equal((await api('post', prefix + '/auth/login').send({ email: actor.email, password: secret })).status, 401);
    assert.equal((await api('post', prefix + '/auth/password-recovery/reset').send({ token: payload.token, newPassword: secret })).status, 400);
    assert.equal((await api('post', prefix + '/auth/password-recovery/request').send({ email: actor.email })).status, 202);
    assert.equal(await IdentityDelivery.countDocuments({ userId: actor.id, consumedAt: null }), 0);
    assert.equal(await IdentityAudit.countDocuments({ action: 'STAFF_REVOKED', subject: actor.id }), 1);
  });
  await t.test('retained availability for revoked or reassigned doctors cannot receive new bookings', async () => {
    const { Availability } = require('../dist/models/Availability');
    const { Appointment } = require('../dist/models/Appointment');
    for (const action of ['revoke', 'role']) {
      const actor = await activate(await provision('doctor'));
      const response = await api('post', '/api/availability', actor).send({ date: '2099-08-01', startTime: '09:00', endTime: '10:00' });
      assert.equal(response.status, 201);
      const id = response.body.availability._id;
      const changed = await api(action === 'revoke' ? 'post' : 'patch', prefix + `/staff/${actor.id}/${action}`, admin)
        .send({ reason: 'SYNTHETIC clinician offboarding', currentPassword: secret, ...(action === 'role' ? { role: 'technician' } : {}) });
      assert.equal(changed.status, 200);
      assert.equal((await api('post', '/api/appointments', patient).send({ availabilityId: id })).status, 409);
      assert.equal((await Availability.findById(id)).isBooked, false);
      assert.equal(await Appointment.countDocuments({ availabilityId: id }), 0);
      assert.ok(await User.findById(actor.id));
    }
  });
  await t.test('revoking an invited staff account prevents activation', async () => {
    const invited = await provision('doctor');
    const payload = await consumeDelivery(invited.deliveryId, 'synthetic-test-operator');
    assert.equal((await api('post', prefix + `/staff/${invited.id}/revoke`, admin).send({ reason: 'SYNTHETIC cancelled onboarding', currentPassword: secret })).status, 200);
    assert.equal((await api('post', prefix + '/auth/password-recovery/reset').send({ token: payload.token, newPassword: secret })).status, 400);
  });
  await t.test('admins cannot revoke/change themselves or administer using client role claims', async () => {
    for (const path of [`/staff/${admin.id}/revoke`, `/staff/${admin.id}/role`, `/staff/${admin.id.toUpperCase()}/revoke`, `/staff/${admin.id.toUpperCase()}/role`]) {
      const method = path.endsWith('/role') ? 'patch' : 'post';
      assert.equal((await api(method, prefix + path, admin).send({ reason: 'SYNTHETIC', currentPassword: secret, ...(method === 'patch' ? { role: 'doctor' } : {}) })).status, 409);
    }
    const forged = { ...patient, token: jwt.sign({ ...jwt.decode(patient.token), role: 'admin' }, config.jwt.secret) };
    assert.equal((await api('get', prefix + '/me', forged)).body.role, 'patient');
    assert.equal((await api('post', prefix + '/staff', forged).send({})).status, 403);
  });
  await t.test('JWT issuer/audience/required claims/algorithm/lifetime are enforced', async () => {
    const claims = jwt.decode(patient.token);
    assert.equal(claims.exp - claims.iat, 900);
    assert.equal(claims.iss, config.jwt.issuer); assert.equal(claims.aud, config.jwt.audience);
    const variants = [
      { ...claims, iss: 'untrusted' }, { ...claims, aud: 'clinical' }, { ...claims, ver: 2 },
      { ...claims, sid: crypto.randomUUID() }, { ...claims, exp: claims.iat + 901 },
      { ...claims, iat: Math.floor(Date.now() / 1000) + 60 },
      Object.fromEntries(Object.entries(claims).filter(([key]) => key !== 'exp')),
    ];
    for (const payload of variants) {
      assert.equal((await api('get', prefix + '/me', { token: jwt.sign(payload, config.jwt.secret) })).status, 401);
    }
    assert.equal((await api('get', prefix + '/me', { token: jwt.sign(claims, config.jwt.secret, { algorithm: 'HS384' }) })).status, 401);
    assert.equal((await api('get', prefix + '/me', { token: jwt.sign({}, config.jwt.secret, { subject: patient.id, expiresIn: 900 }) })).status, 401);
  });
  await t.test('JWT TTL cannot be configured outside bounds and delivery key is mandatory', async () => {
    for (const extra of [{ JWT_TTL_SECONDS: '0' }, { JWT_TTL_SECONDS: '901' }, { JWT_TTL_SECONDS: '60.5' }, { IDENTITY_DELIVERY_KEY: '' }]) {
      const child = spawnSync(process.execPath, ['-e', "require('./dist/config')"], { cwd: require('node:path').resolve(__dirname, '..'), env: { ...process.env, ...extra } });
      assert.notEqual(child.status, 0);
    }
  });
  await t.test('logout revokes one session and logout-all invalidates the full user session set', async () => {
    const first = await register(); const second = await login(first.email);
    assert.equal((await api('post', prefix + '/auth/logout', first)).status, 204);
    assert.equal((await api('get', prefix + '/me', first)).status, 401);
    assert.equal((await api('get', prefix + '/me', second)).status, 200);
    const third = await login(first.email);
    assert.equal((await api('post', prefix + '/auth/logout-all', second)).status, 204);
    for (const actor of [second, third]) assert.equal((await api('get', prefix + '/me', actor)).status, 401);
    assert.equal((await api('get', prefix + '/me', patient)).status, 200);
  });
  await t.test('password change requires the current password and invalidates all sessions', async () => {
    const actor = await register(); const second = await login(actor.email);
    assert.equal((await api('post', prefix + '/auth/password/change', actor).send({ currentPassword: 'wrong', newPassword: 'Synthetic-New-Password!' })).status, 401);
    assert.equal((await api('get', prefix + '/me', actor)).status, 200);
    assert.equal((await api('post', prefix + '/auth/password/change', actor).send({ currentPassword: secret, newPassword: 'Synthetic-New-Password!' })).status, 204);
    for (const session of [actor, second]) assert.equal((await api('get', prefix + '/me', session)).status, 401);
    resetLimits();
    assert.equal((await api('post', prefix + '/auth/login').send({ email: actor.email, password: secret })).status, 401);
    assert.equal((await login(actor.email, 'Synthetic-New-Password!')).id, actor.id);
  });
  await t.test('recovery is non-enumerating, rate-bounded and does not log out users on request', async () => {
    const actor = await register();
    const known = await api('post', prefix + '/auth/password-recovery/request').send({ email: actor.email });
    const unknown = await api('post', prefix + '/auth/password-recovery/request').send({ email: 'absent@example.test' });
    assert.equal(known.status, 202); assert.deepEqual(known.body, unknown.body);
    assert.equal(JSON.stringify(known.body).includes('token'), false);
    assert.equal((await api('get', prefix + '/me', actor)).status, 200);
    assert.equal((await api('post', prefix + '/auth/password-recovery/request').send({ email: actor.email })).status, 202);
    assert.equal(await IdentityDelivery.countDocuments({ userId: actor.id, consumedAt: null }), 1);
    for (let i = 0; i < 2; i++) await api('post', prefix + '/auth/password-recovery/request').send({ email: 'absent@example.test' });
    assert.equal((await api('post', prefix + '/auth/password-recovery/request').send({ email: 'absent@example.test' })).status, 429);
  });
  await t.test('recovery stores a token hash and encrypted envelope, clears handoff and never auto-logs-in', async () => {
    const actor = await register(); const second = await login(actor.email);
    const { payload, delivery } = await recovery(actor);
    const record = await IdentityChallenge.findById(tokenHash(payload.token));
    assert.equal(record.userId.toString(), actor.id);
    assert.equal(JSON.stringify(delivery).includes(payload.token), false);
    assert.equal(JSON.stringify(record).includes(payload.token), false);
    const result = await api('post', prefix + '/auth/password-recovery/reset').send({ token: payload.token, newPassword: 'Synthetic-Recovered-Password!' });
    assert.equal(result.status, 204); assert.equal(result.text, '');
    for (const session of [actor, second]) assert.equal((await api('get', prefix + '/me', session)).status, 401);
    assert.equal((await api('post', prefix + '/auth/password-recovery/reset').send({ token: payload.token, newPassword: secret })).status, 400);
    assert.equal((await login(actor.email, 'Synthetic-Recovered-Password!')).role, 'patient');
    const audit = JSON.stringify(await IdentityAudit.find({ subject: actor.id }));
    for (const sensitive of [payload.token, secret, actor.email, 'Synthetic-Recovered-Password!']) assert.equal(audit.includes(sensitive), false);
  });
  await t.test('concurrent reset consumption permits one password change only', async () => {
    const actor = await register(); const { payload } = await recovery(actor);
    const results = await Promise.all(['Synthetic-Concurrent-A!', 'Synthetic-Concurrent-B!'].map(newPassword => api('post', prefix + '/auth/password-recovery/reset').send({ token: payload.token, newPassword })));
    assert.deepEqual(results.map(r => r.status).sort(), [204, 400]);
    assert.equal(await IdentityAudit.countDocuments({ subject: actor.id, action: 'PASSWORD_RECOVERED' }), 1);
  });
  await t.test('expired recovery tokens and expired stored sessions fail without relying on TTL cleanup', async () => {
    const actor = await register(); const { payload } = await recovery(actor);
    await IdentityChallenge.updateOne({ _id: tokenHash(payload.token) }, { $set: { expiresAt: new Date(Date.now() - 1000) } });
    assert.equal((await api('post', prefix + '/auth/password-recovery/reset').send({ token: payload.token, newPassword: secret })).status, 400);
    const claims = jwt.decode(actor.token);
    await IdentitySession.updateOne({ _id: claims.sid }, { $set: { expiresAt: new Date(Date.now() - 1000) } });
    assert.equal((await api('get', prefix + '/me', actor)).status, 401);
  });
  await t.test('a new recovery request supersedes old challenges without silently changing account identity', async () => {
    const actor = await register(); const first = await recovery(actor); const second = await recovery(actor);
    assert.equal((await api('post', prefix + '/auth/password-recovery/reset').send({ token: first.payload.token, newPassword: secret })).status, 400);
    assert.equal((await api('post', prefix + '/auth/password-recovery/reset').send({ token: second.payload.token, newPassword: secret })).status, 204);
    const user = await User.findById(actor.id);
    assert.equal(user.email, actor.email); assert.equal(user.role, 'patient');
  });
  await t.test('concurrent delivery handoff is single use; tampered encrypted content cannot be consumed', async () => {
    const invited = await provision('technician');
    const outcomes = await Promise.allSettled([consumeDelivery(invited.deliveryId, 'synthetic-operator'), consumeDelivery(invited.deliveryId, 'synthetic-operator')]);
    assert.equal(outcomes.filter(r => r.status === 'fulfilled').length, 1);
    const tampered = await provision('doctor');
    await IdentityDelivery.updateOne({ _id: tampered.deliveryId }, { $set: { tag: '00'.repeat(16) } });
    await assert.rejects(consumeDelivery(tampered.deliveryId, 'synthetic-operator'));
    assert.equal((await IdentityDelivery.findById(tampered.deliveryId)).consumedAt, null);
  });
  await t.test('session/audit storage failures fail closed and transactional provisioning/revocation roll back', async () => {
    const originalFind = IdentitySession.findOne;
    IdentitySession.findOne = async () => { throw new Error('Synthetic session store failure'); };
    try { assert.equal((await api('get', prefix + '/me', patient)).status, 500); }
    finally { IdentitySession.findOne = originalFind; }
    const originalAudit = IdentityAudit.create;
    const invited = await provision('doctor'); const actor = await activate(invited);
    const sessions = await IdentitySession.countDocuments({ userId: patient.id });
    const recoveryFixture = await recovery(patient);
    IdentityAudit.create = async () => { throw new Error('Synthetic audit store failure'); };
    try {
      assert.equal((await api('post', prefix + '/auth/login').send({ email: patient.email, password: secret })).status, 500);
      assert.equal(await IdentitySession.countDocuments({ userId: patient.id }), sessions);
      assert.equal((await api('post', prefix + '/staff', admin).send({ email: 'rollback@example.test', name: 'Synthetic', role: 'doctor', reason: 'SYNTHETIC', currentPassword: secret })).status, 500);
      assert.equal(await User.countDocuments({ email: 'rollback@example.test' }), 0);
      assert.equal((await api('post', prefix + `/staff/${actor.id}/revoke`, admin).send({ reason: 'SYNTHETIC', currentPassword: secret })).status, 500);
      assert.equal((await User.findById(actor.id)).state, 'active');
      assert.equal((await api('post', prefix + '/auth/password-recovery/reset').send({ token: recoveryFixture.payload.token, newPassword: 'Synthetic-Rollback-Password!' })).status, 500);
      assert.equal((await IdentityChallenge.findById(tokenHash(recoveryFixture.payload.token))).usedAt, null);
      assert.equal((await api('get', prefix + '/me', patient)).status, 200);
    } finally { IdentityAudit.create = originalAudit; }
    assert.equal((await api('get', prefix + '/me', actor)).status, 200);
  });
  await t.test('forbidden cross-patient detail, cancellation, filters and session enumeration', async () => {
    const availability = await api('post', '/api/availability', doctor).send({ date: '2099-07-03', startTime: '09:00', endTime: '10:00' });
    assert.equal(availability.status, 201);
    const booking = await api('post', '/api/appointments', patient).send({ availabilityId: availability.body.availability._id });
    assert.equal(booking.status, 201);
    const id = booking.body.appointment._id;
    assert.equal((await api('get', `/api/appointments/${id}`, patient)).status, 200);
    assert.equal((await api('get', `/api/appointments/${id}`, doctor)).status, 200);
    assert.equal((await api('get', `/api/appointments/${id}`, otherPatient)).status, 404);
    assert.equal((await api('patch', `/api/appointments/${id}/cancel`, otherPatient)).status, 409);
    assert.equal((await api('get', `/api/appointments?patientId=${patient.id}`, otherPatient)).status, 400);
    assert.equal((await api('get', '/api/appointments', otherPatient)).body.appointments.length, 0);
    for (const actor of [technician, admin]) assert.equal((await api('get', `/api/appointments/${id}`, actor)).status, 403);
    const sessions = await api('get', prefix + '/sessions', otherPatient);
    assert.equal(sessions.status, 200);
    assert.equal(sessions.body.sessions.some(s => s._id === jwt.decode(patient.token).sid), false);
    assert.equal((await api('get', prefix + `/staff/${doctor.id}/audit`, patient)).status, 403);
  });
  await t.test('versioned principal/introspection has no legacy clinical identity or client-controlled role', async () => {
    const me = await api('get', prefix + '/me', patient);
    assert.equal(me.status, 200); assert.equal(me.headers['cache-control'], 'no-store');
    assert.deepEqual(Object.keys(me.body).sort(), ['schemaVersion', 'issuer', 'subject', 'role', 'sessionId', 'expiresAt'].sort());
    const schema = require('../contracts/identity-v1.schema.json');
    assert.deepEqual(Object.keys(me.body).sort(), [...schema.required].sort());
    assert.match(me.body.subject, new RegExp(schema.properties.subject.pattern));
    assert.ok(schema.properties.role.enum.includes(me.body.role));
    assert.equal(me.body.schemaVersion, schema.properties.schemaVersion.const);
    assert.equal(me.body.issuer, schema.properties.issuer.const);
    assert.ok(Number.isInteger(me.body.expiresAt));
    assert.equal(me.body.subject, patient.id);
    const check = await api('post', prefix + '/introspect', patient).send({});
    assert.deepEqual(check.body, { active: true, ...me.body });
    const introspection = require('../contracts/introspection-v1.schema.json');
    assert.deepEqual(Object.keys(check.body).sort(), [...introspection.required].sort());
    assert.equal((await api('post', prefix + '/introspect', patient).send({ role: 'admin', subject: otherPatient.id })).status, 400);
    for (const method of ['get', 'post']) {
      const target = api(method, prefix + (method === 'get' ? '/me' : '/introspect')).set('Cookie', 'streamlit_user=doctor; role=admin').set('X-User-Role', 'admin');
      assert.equal((await target).status, 401);
    }
    assert.equal((await api('get', prefix + '/me').set('Authorization', 'Bearer ' + JSON.stringify({ user: 'physician', role: 'admin' }))).status, 401);
  });
  await t.test('actual operator CLI bootstraps and hands off one synthetic invitation without default credentials', async () => {
    const result = await operatorCli('bootstrap', ['synthetic-cli-operator', 'cli-admin@example.test', 'Synthetic CLI Admin', 'SYNTHETIC bootstrap change'], 'synthetic_operator_test');
    assert.equal(result.code, 0);
    const created = JSON.parse(result.output);
    assert.match(created.id, /^[a-f0-9]{24}$/);
    const handoff = await operatorCli('deliver', ['synthetic-cli-operator', created.deliveryId, 'HANDOFF'], 'synthetic_operator_test');
    assert.equal(handoff.code, 0);
    const delivered = JSON.parse(handoff.output);
    assert.equal(delivered.email, 'cli-admin@example.test');
    assert.equal(delivered.kind, 'activation');
    assert.match(delivered.token, /^[a-f0-9]{64}$/);
    const replay = await operatorCli('deliver', ['synthetic-cli-operator', created.deliveryId, 'HANDOFF'], 'synthetic_operator_test');
    assert.notEqual(replay.code, 0); assert.equal(replay.output, '');
  });
  await t.test('mutual concurrent admin revocation cannot remove every active administrator', async () => {
    const other = await activate(await provision('admin'));
    const responses = await Promise.all([
      api('post', prefix + `/staff/${other.id}/revoke`, admin).send({ reason: 'SYNTHETIC concurrent revocation A', currentPassword: secret }),
      api('post', prefix + `/staff/${admin.id}/revoke`, other).send({ reason: 'SYNTHETIC concurrent revocation B', currentPassword: secret }),
    ]);
    assert.deepEqual(responses.map(r => r.status).sort(), [200, 401]);
    assert.equal(await User.countDocuments({ role: 'admin', state: 'active' }), 1);
  });
});

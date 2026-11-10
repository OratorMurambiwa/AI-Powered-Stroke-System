const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const mongoose = require('mongoose');
const jwt = require('jsonwebtoken');
const request = require('supertest');
// Refuse all default/persistent databases. The test runner supplies a tmpfs replica set.
if (!process.env.TEST_MONGODB_URI || !process.env.TEST_MONGODB_URI.includes('stroke-booking-mongo:27017')) {
  throw new Error('Tests require the dedicated synthetic MongoDB fixture');
}
process.env.NODE_ENV = 'test';
process.env.JWT_SECRET = crypto.randomBytes(48).toString('hex');
process.env.IDENTITY_DELIVERY_KEY = crypto.randomBytes(32).toString('hex');
process.env.MONGODB_URI = process.env.TEST_MONGODB_URI;
process.env.RATE_LIMIT_MAX_REQUESTS = '1000';
const app = require('../dist/app').default;
const { User } = require('../dist/models/User');
const { Availability } = require('../dist/models/Availability');
const { Appointment } = require('../dist/models/Appointment');
const { connectDB, disconnectDB } = require('../dist/config/database');
const { authLimiter, bookingLimiter } = require('../dist/middleware/rateLimiter');
let doctor, otherDoctor, patient, otherPatient, admin;
const tokens = new Map();
const token = user => tokens.get(user.id);
const as = (method, path, user) => request(app)[method](path).set('Authorization', `Bearer ${token(user)}`);
const date = '2099-06-01';
async function slot(startTime = '09:00', endTime = '10:00', user = doctor) {
  return as('post', '/api/availability', user).send({ date, startTime, endTime });
}
function resetLimits() {
  for (const limiter of [authLimiter, bookingLimiter]) {
    limiter.resetKey('::ffff:127.0.0.1');
    limiter.resetKey('127.0.0.1');
    limiter.resetKey('::/56');
  }
}
before(async () => {
  await connectDB();
  // Staff provisioning is fixture-only direct persistence, never public signup.
  [doctor, otherDoctor, patient, otherPatient, admin] = await User.create([
    ['doctor', 'doctor'], ['otherdoctor', 'doctor'], ['patient', 'patient'], ['otherpatient', 'patient'], ['admin', 'admin'],
  ].map(([name, role]) => ({ email: `${name}@example.test`, name: `Synthetic ${name}`, password: 'Synthetic-only-Password!', role })));
  for (const user of [doctor, otherDoctor, patient, otherPatient, admin]) {
    const login = await request(app).post('/api/auth/login').send({ email: user.email, password: 'Synthetic-only-Password!' });
    assert.equal(login.status, 200);
    tokens.set(user.id, login.body.token);
  }
});
after(async () => { await disconnectDB(); });

test('authentication, schedule and booking integration against real MongoDB', async t => {
  await t.test('configuration rejects absent or weak JWT signing secrets', async () => {
    for (const JWT_SECRET of ['', 'your-secret-key']) {
      const child = spawnSync(process.execPath, ['-e', "require('./dist/config')"], {
        cwd: require('node:path').resolve(__dirname, '..'), env: { ...process.env, JWT_SECRET }, encoding: 'utf8',
      });
      assert.notEqual(child.status, 0);
      assert.match(child.stderr, /JWT_SECRET must contain at least 32 bytes/);
    }
  });

  await t.test('signup hashes password, normalizes email, exposes no password and logs in', async () => {
    resetLimits();
    const result = await request(app).post('/api/auth/register').send({ name: 'Synthetic Signup', email: 'SIGNUP@EXAMPLE.TEST', password: 'Synthetic-signup-Password!' });
    assert.equal(result.status, 201);
    assert.equal(result.body.user.role, 'patient');
    assert.equal(result.body.user.password, undefined);
    const stored = await User.findById(result.body.user.id).select('+password');
    assert.notEqual(stored.password, 'Synthetic-signup-Password!');
    assert.equal(await stored.comparePassword('Synthetic-signup-Password!'), true);
    const login = await request(app).post('/api/auth/login').send({ email: 'signup@example.test', password: 'Synthetic-signup-Password!' });
    assert.equal(login.status, 200);
    assert.equal(jwt.verify(login.body.token, process.env.JWT_SECRET).sub, stored.id);
  });
  await t.test('public signup refuses doctor/admin and malformed input; duplicate email is 409', async () => {
    for (const role of ['doctor', 'admin']) {
      resetLimits();
      const result = await request(app).post('/api/auth/register').send({ name: 'Synthetic Escalation', email: `${role}-signup@example.test`, password: 'Synthetic-only-Password!', role });
      assert.equal(result.status, 400);
      assert.equal(await User.countDocuments({ email: `${role}-signup@example.test` }), 0);
    }
    for (const body of [
      { email: { $ne: null }, password: 'Synthetic-only-Password!' },
      { email: 'invalid', password: 'Synthetic-only-Password!' },
      { email: 'bad@example.test', password: 'short', name: 'Synthetic' },
      { email: 'bad@example.test', password: 'é'.repeat(40), name: 'Synthetic' },
    ]) {
      resetLimits();
      assert.equal((await request(app).post('/api/auth/register').send(body)).status, 400);
    }
    resetLimits();
    assert.equal((await request(app).post('/api/auth/register').send({ email: 'SIGNUP@example.test', name: 'Synthetic Duplicate', password: 'Synthetic-only-Password!' })).status, 409);
  });
  await t.test('wrong credentials, malformed and expired tokens fail closed', async () => {
    resetLimits();
    assert.equal((await request(app).post('/api/auth/login').send({ email: patient.email, password: 'incorrect' })).status, 401);
    assert.equal((await request(app).get('/api/appointments')).status, 401);
    for (const credential of ['invalid', jwt.sign({}, process.env.JWT_SECRET, { subject: patient.id, expiresIn: -1 })]) {
      assert.equal((await request(app).get('/api/appointments').set('Authorization', `Bearer ${credential}`)).status, 401);
    }
  });
  await t.test('forged token role does not confer access; revoked persisted role takes effect', async () => {
    const forged = jwt.sign({ ...jwt.decode(token(patient)), role: 'admin' }, process.env.JWT_SECRET);
    assert.equal((await request(app).post('/api/availability').set('Authorization', `Bearer ${forged}`).send({ date, startTime: '08:00', endTime: '09:00' })).status, 403);
    const oldToken = token(otherDoctor);
    await User.updateOne({ _id: otherDoctor._id }, { $set: { role: 'patient' } });
    assert.equal((await request(app).post('/api/availability').set('Authorization', `Bearer ${oldToken}`).send({ date, startTime: '08:00', endTime: '09:00' })).status, 401);
    await User.updateOne({ _id: otherDoctor._id }, { $set: { role: 'doctor' } });
  });
  await t.test('only doctors publish availability; invalid dates/times and injection rejected', async () => {
    for (const user of [patient, admin]) assert.equal((await slot('08:00', '09:00', user)).status, 403);
    for (const body of [
      { date: '2099-02-30', startTime: '08:00', endTime: '09:00' },
      { date, startTime: '25:00', endTime: '26:00' },
      { date, startTime: '10:00', endTime: '09:00' },
      { date: '2000-01-01', startTime: '08:00', endTime: '09:00' },
      { date, startTime: '08:00', endTime: '09:00', isBooked: false },
    ]) assert.equal((await as('post', '/api/availability', doctor).send(body)).status, 400);
    assert.equal((await request(app).get('/api/availability?doctorId[$ne]=null')).status, 400);
    assert.equal((await request(app).get('/api/availability?date=not-a-date')).status, 400);
  });
  await t.test('overlapping concurrent schedule creation admits one interval; adjacent allowed', async () => {
    const results = await Promise.all([slot('09:00', '10:00'), slot('09:30', '10:30')]);
    assert.deepEqual(results.map(r => r.status).sort(), [201, 409]);
    // Use a separate interval independent of which concurrent request won.
    assert.equal((await slot('11:00', '12:00')).status, 201);
    assert.equal((await slot('12:00', '13:00')).status, 201);
    const query = await request(app).get(`/api/availability?doctorId=${doctor.id}&date=${date}&availableOnly=true`);
    assert.equal(query.status, 200);
    assert.equal(query.body.availability.length, 3);
  });
  await t.test('availability ownership, update overlap and deletion are enforced', async () => {
    const created = await slot('13:00', '14:00');
    const id = created.body.availability._id;
    assert.equal((await as('put', `/api/availability/${id}`, otherDoctor).send({ date, startTime: '14:00', endTime: '15:00' })).status, 409);
    assert.equal((await as('put', `/api/availability/${id}`, doctor).send({ date, startTime: '11:30', endTime: '12:30' })).status, 409);
    assert.equal((await as('put', `/api/availability/${id}`, doctor).send({ date, startTime: '14:00', endTime: '15:00' })).status, 200);
    assert.equal((await as('delete', `/api/availability/${id}`, otherDoctor)).status, 409);
    assert.equal((await as('delete', `/api/availability/${id}`, doctor)).status, 204);
  });
  let booked, bookedSlot;
  await t.test('six concurrent booking attempts persist exactly one appointment', async () => {
    resetLimits();
    bookedSlot = (await slot('15:00', '16:00')).body.availability;
    const results = await Promise.all(Array.from({ length: 6 }, (_, i) =>
      as('post', '/api/appointments', i % 2 ? patient : otherPatient).send({ availabilityId: bookedSlot._id, notes: 'Synthetic appointment only' })));
    assert.deepEqual(results.map(r => r.status).sort(), [201, 409, 409, 409, 409, 409]);
    booked = results.find(r => r.status === 201).body.appointment;
    assert.equal(await Appointment.countDocuments({ availabilityId: bookedSlot._id, status: 'confirmed' }), 1);
    assert.equal((await Availability.findById(bookedSlot._id)).isBooked, true);
  });
  await t.test('booked slots cannot be edited/deleted/reopened; only patients book', async () => {
    assert.equal((await as('put', `/api/availability/${bookedSlot._id}`, doctor).send({ date, startTime: '16:00', endTime: '17:00' })).status, 409);
    assert.equal((await as('put', `/api/availability/${bookedSlot._id}`, doctor).send({ date, startTime: '15:00', endTime: '16:00', isBooked: false })).status, 400);
    assert.equal((await as('delete', `/api/availability/${bookedSlot._id}`, doctor)).status, 409);
    assert.equal((await as('post', '/api/appointments', doctor).send({ availabilityId: bookedSlot._id })).status, 403);
    assert.equal((await as('post', '/api/appointments', patient).send({ availabilityId: 'bad' })).status, 400);
  });
  await t.test('appointment lists respect identity and date filters; cancellation checks ownership', async () => {
    const owner = booked.patientId === patient.id ? patient : otherPatient;
    const stranger = booked.patientId === patient.id ? otherPatient : patient;
    const mine = await as('get', `/api/appointments?date=${date}&status=confirmed`, owner);
    assert.equal(mine.body.appointments.length, 1);
    assert.equal((await as('get', '/api/appointments', stranger)).body.appointments.length, 0);
    assert.equal((await as('get', '/api/appointments', doctor)).body.appointments.length, 1);
    assert.equal((await as('get', '/api/appointments', otherDoctor)).body.appointments.length, 0);
    assert.equal((await as('patch', `/api/appointments/${booked._id}/cancel`, stranger)).status, 409);
    const cancellations = await Promise.all([
      as('patch', `/api/appointments/${booked._id}/cancel`, owner),
      as('patch', `/api/appointments/${booked._id}/cancel`, owner),
    ]);
    assert.deepEqual(cancellations.map(r => r.status).sort(), [200, 409]);
    assert.equal((await Availability.findById(bookedSlot._id)).isBooked, false);
    resetLimits();
    assert.equal((await as('post', '/api/appointments', stranger).send({ availabilityId: bookedSlot._id })).status, 201);
    assert.equal((await as('patch', `/api/appointments/${booked._id}/cancel`, owner)).status, 409);
    assert.equal((await Availability.findById(bookedSlot._id)).isBooked, true);
  });
  await t.test('unique index independently rejects duplicate confirmed appointments', async () => {
    const current = await Appointment.findOne({ availabilityId: bookedSlot._id, status: 'confirmed' }).lean();
    const { _id, __v, ...copy } = current;
    await assert.rejects(Appointment.create(copy), error => error.code === 11000);
  });
  await t.test('transaction rolls slot back if appointment persistence fails', async () => {
    resetLimits();
    const available = (await slot('17:00', '18:00')).body.availability;
    const original = Appointment.create;
    Appointment.create = async () => { throw new Error('Synthetic storage fault'); };
    try {
      assert.equal((await as('post', '/api/appointments', patient).send({ availabilityId: available._id })).status, 500);
    } finally { Appointment.create = original; }
    assert.equal((await Availability.findById(available._id)).isBooked, false);
    assert.equal(await Appointment.countDocuments({ availabilityId: available._id }), 0);
    assert.equal((await as('post', '/api/appointments', patient).send({ availabilityId: available._id })).status, 201);
  });
  await t.test('booking races against edit/delete preserve slot and appointment consistency', async () => {
    for (const operation of ['put', 'delete']) {
      resetLimits();
      const slotId = (await slot(operation === 'put' ? '18:00' : '19:00', operation === 'put' ? '19:00' : '20:00')).body.availability._id;
      let change = as(operation, `/api/availability/${slotId}`, doctor);
      if (operation === 'put') change = change.send({ date, startTime: '20:00', endTime: '21:00' });
      const [booking, editing] = await Promise.all([
        as('post', '/api/appointments', patient).send({ availabilityId: slotId }), change,
      ]);
      assert.ok([201, 409].includes(booking.status));
      assert.ok([200, 204, 409].includes(editing.status));
      const persistedSlot = await Availability.findById(slotId);
      const appointment = await Appointment.findOne({ availabilityId: slotId, status: 'confirmed' });
      if (appointment) {
        assert.equal(persistedSlot.isBooked, true);
        assert.equal(persistedSlot.startTime, appointment.startTime);
        assert.equal(persistedSlot.endTime, appointment.endTime);
      } else assert.ok(!persistedSlot || !persistedSlot.isBooked);
    }
  });
});

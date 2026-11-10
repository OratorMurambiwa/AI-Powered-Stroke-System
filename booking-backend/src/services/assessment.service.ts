import { createHash, randomUUID } from 'node:crypto';
import mongoose from 'mongoose';
import { Appointment, IAppointment } from '../models/Appointment';
import { AssessmentRequest } from '../models/AssessmentRequest';
import { User } from '../models/User';
import { assertActor, Principal } from './identity.service';
import { canonicalRole } from '../identity/roles';
import { fields, HttpError } from '../utils/http';
import { config } from '../config';
export function uuid(value: unknown): string {
  if (typeof value !== 'string' || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value)) throw new HttpError(400, 'invalid_uuid');
  return value;
}
const hash = (values: unknown[]) => createHash('sha256').update(JSON.stringify(values)).digest('hex');
export function appointmentDto(record: IAppointment) {
  if (!record.appointmentUuid) throw new HttpError(409, 'appointment_requires_explicit_uuid_adoption');
  return { schemaVersion: 1, appointmentId: record.appointmentUuid, patientSubject: String(record.patientId), doctorSubject: String(record.doctorId),
    date: record.date.toISOString().slice(0, 10), startTime: record.startTime, endTime: record.endTime, status: record.status,
    assessmentRequestId: record.assessmentRequestId ?? null, encounterId: record.encounterId ?? null };
}
export function clinicalUrl(): string {
  try {
    if (!config.clinicalApiUrl) throw new Error();
    const url = new URL(config.clinicalApiUrl);
    if (!['http:', 'https:'].includes(url.protocol) || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || url.username || url.password || url.search || url.hash || url.pathname !== '/api/v1/clinical/assessment-requests') throw new Error();
    return url.toString();
  } catch { throw new HttpError(503, 'clinical_service_not_configured'); }
}
function command(record: any) {
  return { schemaVersion: 1, mode: 'SCHEDULED', requestId: record.id, appointmentId: record.appointmentId, encounterId: record.encounterId,
    sourceId: record.sourceId, patientId: record.patientId, patientMappingId: record.patientMappingId, clinicianMappingId: record.clinicianMappingId };
}
export function result(record: any) {
  return { schemaVersion: 1, requestId: record.id, appointmentId: record.appointmentId, encounterId: record.encounterId,
    state: record.state, errorCode: record.lastErrorCode ?? null, retryable: record.state === 'PENDING' };
}
export async function ownedAppointment(actor: Principal, id: string) {
  const scope = actor.role === 'patient' ? { patientId: actor.id } : actor.role === 'doctor' ? { doctorId: actor.id } : null;
  if (!scope) throw new HttpError(403, 'clinical_access_forbidden');
  const record = await Appointment.findOne({ appointmentUuid: uuid(id), ...scope });
  if (!record) throw new HttpError(404, 'appointment_not_found');
  return record;
}
export async function reserve(actor: Principal, appointmentId: string, raw: unknown) {
  if (actor.role !== 'doctor') throw new HttpError(403, 'assigned_doctor_required');
  const body = fields(raw, ['schemaVersion', 'requestId', 'sourceId', 'patientId', 'patientMappingId', 'clinicianMappingId']);
  if (body.schemaVersion !== 1) throw new HttpError(400, 'unsupported_contract_version');
  const id = uuid(body.requestId); appointmentId = uuid(appointmentId);
  for (const name of ['sourceId', 'patientId', 'patientMappingId', 'clinicianMappingId']) uuid(body[name]);
  const intentHash = hash([1, appointmentId, id, body.sourceId, body.patientId, body.patientMappingId, body.clinicianMappingId]);
  clinicalUrl(); // Missing configuration must not reserve/lock an appointment.
  return mongoose.connection.transaction(async session => {
    await assertActor(actor, session, ['doctor']);
    const appointment = await Appointment.findOne({ appointmentUuid: appointmentId, doctorId: actor.id }).session(session);
    if (!appointment) throw new HttpError(404, 'appointment_not_found');
    const existing = await AssessmentRequest.findById(id).session(session);
    if (existing) {
      if (existing.intentHash !== intentHash || String(existing.actorId) !== actor.id || existing.actorRoleVersion !== actor.roleVersion) throw new HttpError(409, 'idempotency_conflict');
      return existing;
    }
    if (appointment.status !== 'confirmed') throw new HttpError(409, 'appointment_not_confirmed');
    if (appointment.assessmentRequestId) throw new HttpError(409, 'appointment_assessment_exists');
    const patient = await User.findById(appointment.patientId).session(session);
    if (!patient || patient.role !== 'patient' || (patient.state ?? 'active') !== 'active') throw new HttpError(409, 'patient_identity_unavailable');
    await User.updateOne({ _id: patient._id }, { $inc: { authWriteVersion: 1 } }, { session });
    const encounterId = randomUUID();
    const commandHash = hash([1, 'SCHEDULED', id, appointmentId, encounterId, body.sourceId, body.patientId, body.patientMappingId, body.clinicianMappingId]);
    await Appointment.updateOne({ _id: appointment._id }, { $set: { assessmentRequestId: id } }, { session });
    const [created] = await AssessmentRequest.create([{ _id: id, appointmentId, actorId: actor.id, actorRoleVersion: actor.roleVersion,
      sourceId: body.sourceId, patientId: body.patientId, patientMappingId: body.patientMappingId, clinicianMappingId: body.clinicianMappingId,
      encounterId, intentHash, commandHash, state: 'PENDING', blocking: true }], { session });
    return created;
  });
}
export async function proof(actor: Principal, appointmentId: string, requestId: string) {
  if (actor.role !== 'doctor') throw new HttpError(403, 'assigned_doctor_required');
  return mongoose.connection.transaction(async session => {
    const doctor = await assertActor(actor, session, ['doctor']);
    const record = await AssessmentRequest.findOne({ _id: uuid(requestId), appointmentId: uuid(appointmentId), actorId: actor.id, blocking: true }).session(session);
    const appointment = await Appointment.findOne({ appointmentUuid: appointmentId, doctorId: actor.id, status: 'confirmed', assessmentRequestId: requestId }).session(session);
    if (!record || !appointment || record.actorRoleVersion !== actor.roleVersion) throw new HttpError(409, 'assessment_request_not_active');
    const patient = await User.findById(appointment.patientId).session(session);
    if (!patient || patient.role !== 'patient' || (patient.state ?? 'active') !== 'active' || canonicalRole(doctor.role) !== 'doctor') throw new HttpError(409, 'appointment_identity_unavailable');
    return { schemaVersion: 1, issuer: config.jwt.issuer, appointmentId, requestId, encounterId: record.encounterId, commandHash: record.commandHash,
      patientSubject: patient.id, patientRoleVersion: patient.clinicalRoleVersion ?? 0,
      doctorSubject: doctor.id, doctorRoleVersion: doctor.clinicalRoleVersion ?? 0,
      actorSubject: actor.id, actorRoleVersion: actor.roleVersion, sessionId: actor.sessionId, status: 'RESERVED', expiresAt: Math.floor(Date.now() / 1000) + 60 };
  });
}
async function receive(response: globalThis.Response, expected: any): Promise<any> {
  const length = response.headers.get('content-length');
  if (response.status !== 200 || !response.headers.get('content-type')?.startsWith('application/json') || !length || !/^\d+$/.test(length) || Number(length) > 4096) throw new Error();
  const reader = response.body?.getReader(); if (!reader) throw new Error();
  let bytes = 0; const chunks: Uint8Array[] = [];
  try {
    while (true) { const { done, value } = await reader.read(); if (done) break; bytes += value.length; if (bytes > 4096) throw new Error(); chunks.push(value); }
  } finally { await reader.cancel(); }
  const data = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  const keys = ['schemaVersion', 'mode', 'requestId', 'appointmentId', 'encounterId', 'sourceId', 'patientId', 'clinicianMappingId', 'state', 'errorCode'];
  if (!data || Array.isArray(data) || Object.keys(data).sort().join() !== keys.sort().join() || data.schemaVersion !== 1 || !['CREATED', 'REJECTED'].includes(data.state)) throw new Error();
  for (const key of ['mode', 'requestId', 'appointmentId', 'encounterId', 'sourceId', 'patientId', 'clinicianMappingId']) if (data[key] !== expected[key]) throw new Error();
  if ((data.state === 'CREATED' && data.errorCode !== null) || (data.state === 'REJECTED' && (typeof data.errorCode !== 'string' || !/^[a-z_]{1,80}$/.test(data.errorCode)))) throw new Error();
  return data;
}
export async function deliver(actor: Principal, record: any, bearer: string) {
  if (record.state !== 'PENDING') return record;
  const leaseId = randomUUID();
  const leased = await AssessmentRequest.findOneAndUpdate({ _id: record.id, state: 'PENDING', $or: [{ leaseUntil: null }, { leaseUntil: { $lte: new Date() } }] },
    { $set: { leaseId, leaseUntil: new Date(Date.now() + 4000) }, $inc: { attempts: 1 } }, { new: true });
  if (!leased) return (await AssessmentRequest.findById(record.id))!;
  let receipt;
  try {
    const payload = command(leased);
    const response = await fetch(clinicalUrl(), { method: 'POST', redirect: 'error', signal: AbortSignal.timeout(2000),
      headers: { 'Content-Type': 'application/json', Authorization: bearer }, body: JSON.stringify(payload) });
    receipt = await receive(response, payload);
  } catch {
    await AssessmentRequest.updateOne({ _id: record.id, state: 'PENDING', leaseId }, { $set: { lastErrorCode: 'clinical_outcome_unknown' } });
    return (await AssessmentRequest.findById(record.id))!; // Never release a lock on ambiguous failure.
  }
  return mongoose.connection.transaction(async session => {
    const current = await AssessmentRequest.findOneAndUpdate({ _id: record.id, state: 'PENDING', leaseId },
      { $set: { state: receipt.state, blocking: receipt.state === 'CREATED', lastErrorCode: receipt.errorCode } }, { new: true, session });
    if (!current) return (await AssessmentRequest.findById(record.id).session(session))!;
    const appointmentFilter = { appointmentUuid: record.appointmentId, assessmentRequestId: record.id, doctorId: record.actorId, status: 'confirmed' };
    const updated = receipt.state === 'CREATED'
      ? await Appointment.updateOne(appointmentFilter, { $set: { encounterId: record.encounterId } }, { session })
      : await Appointment.updateOne(appointmentFilter, { $unset: { assessmentRequestId: '' } }, { session });
    if (updated.matchedCount !== 1) throw new HttpError(503, 'assessment_reservation_mismatch');
    return current;
  });
}

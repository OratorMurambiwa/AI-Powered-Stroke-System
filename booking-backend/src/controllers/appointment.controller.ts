import mongoose from 'mongoose';
import { Appointment } from '../models/Appointment';
import { Availability } from '../models/Availability';
import { User } from '../models/User';
import { canonicalRole } from '../identity/roles';
import { assertActor } from '../services/identity.service';
import { AuthRequest } from '../middleware/auth';
import { fields, objectId, text, day, HttpError, route } from '../utils/http';

export const createAppointment = route(async (req: AuthRequest, res) => {
  const body = fields(req.body, ['availabilityId', 'notes']);
  const availabilityId = objectId(body.availabilityId);
  const notes = body.notes === undefined ? undefined : text(body.notes, 2000);
  const appointment = await mongoose.connection.transaction(async session => {
    const patient = await assertActor(req.user!, session, ['patient']);
    if (!patient) throw new HttpError(403, 'A patient account is required');
    // Atomic compare-and-set. withTransaction retries transient write conflicts.
    const slot = await Availability.findOneAndUpdate({ _id: availabilityId, isBooked: false }, { $set: { isBooked: true } }, { session, new: true });
    if (!slot) throw new HttpError(409, 'Slot unavailable');
    const clinician = await User.findById(slot.doctorId).session(session);
    if (!clinician || canonicalRole(clinician.role) !== 'doctor' || (clinician.state ?? 'active') !== 'active') {
      throw new HttpError(409, 'Clinician is not available for new bookings');
    }
    // Serialize new bookings with clinician revocation/reassignment; retain old records.
    await User.updateOne({ _id: clinician._id }, { $inc: { authWriteVersion: 1 } }, { session });
    if (new Date(slot.date.toISOString().slice(0, 10) + 'T' + slot.startTime + ':00Z').getTime() <= Date.now()) throw new HttpError(409, 'Slot is in the past');
    const [created] = await Appointment.create([{
      patientId: patient._id, patientName: patient.name, doctorId: slot.doctorId,
      doctorName: slot.doctorName, availabilityId: slot._id, date: slot.date,
      startTime: slot.startTime, endTime: slot.endTime, status: 'confirmed', notes,
    }], { session });
    return created;
  });
  // No post-commit dependency can turn a persisted booking into an HTTP failure.
  res.status(201).json({ appointment });
});
export const getAppointments = route(async (req: AuthRequest, res) => {
  fields(req.query, ['status', 'date']);
  const query: mongoose.FilterQuery<InstanceType<typeof Appointment>> = {};
  if (req.user!.role === 'patient') query.patientId = req.user!.id;
  else if (req.user!.role === 'doctor') query.doctorId = req.user!.id;
  else throw new HttpError(403, 'Forbidden');
  if (req.query.status !== undefined) {
    if (!['confirmed', 'cancelled', 'completed'].includes(req.query.status as string)) throw new HttpError(400, 'Invalid status');
    query.status = req.query.status;
  }
  if (req.query.date !== undefined) query.date = day(req.query.date);
  res.json({ appointments: await Appointment.find(query).sort({ date: 1, startTime: 1 }).limit(200) });
});
export const cancelAppointment = route(async (req: AuthRequest, res) => {
  const id = objectId(req.params.id);
  const appointment = await mongoose.connection.transaction(async session => {
    await assertActor(req.user!, session, ['patient', 'doctor']);
    const updated = await Appointment.findOneAndUpdate({
      _id: id, status: 'confirmed', $or: [{ patientId: req.user!.id }, { doctorId: req.user!.id }],
    }, { $set: { status: 'cancelled' } }, { session, new: true });
    if (!updated) throw new HttpError(409, 'Appointment unavailable for cancellation');
    const slot = await Availability.findOneAndUpdate({ _id: updated.availabilityId, isBooked: true }, { $set: { isBooked: false } }, { session });
    if (!slot) throw new Error('Slot invariant failed');
    return updated;
  });
  res.json({ appointment });
});

export const getAppointment = route(async (req: AuthRequest, res) => {
  const id = objectId(req.params.id);
  const query = req.user!.role === 'patient' ? { patientId: req.user!.id } : { doctorId: req.user!.id };
  const appointment = await Appointment.findOne({ _id: id, ...query });
  if (!appointment) throw new HttpError(404, 'Appointment not found');
  res.json({ appointment });
});

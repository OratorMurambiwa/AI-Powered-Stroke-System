import mongoose from 'mongoose';
import { Availability } from '../models/Availability';
import { User } from '../models/User';
import { AuthRequest } from '../middleware/auth';
import { day, times, fields, objectId, HttpError, route } from '../utils/http';

// This persisted write serializes schedule changes across all API processes.
async function lockDoctor(id: string, session: mongoose.ClientSession): Promise<void> {
  const doctor = await User.findOneAndUpdate({ _id: id, role: 'doctor' }, { $inc: { scheduleVersion: 1 } }, { session, new: true });
  if (!doctor) throw new HttpError(403, 'A doctor account is required');
}
function schedule(body: unknown) {
  const data = fields(body, ['date', 'startTime', 'endTime']);
  const date = day(data.date);
  const interval = times(data.startTime, data.endTime);
  if (new Date(date.toISOString().slice(0, 10) + 'T' + interval.startTime + ':00Z').getTime() <= Date.now()) {
    throw new HttpError(400, 'Availability must be in the future');
  }
  return { date, ...interval };
}
export const createAvailability = route(async (req: AuthRequest, res) => {
  const input = schedule(req.body);
  const doctorId = req.user!.id;
  const availability = await mongoose.connection.transaction(async session => {
    await lockDoctor(doctorId, session);
    if (await Availability.exists({ doctorId, date: input.date, startTime: { $lt: input.endTime }, endTime: { $gt: input.startTime } }).session(session)) {
      throw new HttpError(409, 'Overlapping availability');
    }
    const doctor = await User.findById(doctorId).session(session);
    const [slot] = await Availability.create([{ ...input, doctorId, doctorName: doctor!.name, isBooked: false }], { session });
    return slot;
  });
  res.status(201).json({ availability });
});
export const getAvailability = route(async (req, res) => {
  const query: mongoose.FilterQuery<InstanceType<typeof Availability>> = {};
  fields(req.query, ['doctorId', 'date', 'availableOnly']);
  if (req.query.doctorId !== undefined) query.doctorId = objectId(req.query.doctorId);
  if (req.query.date !== undefined) query.date = day(req.query.date);
  if (req.query.availableOnly !== undefined) {
    if (!['true', 'false'].includes(req.query.availableOnly as string)) throw new HttpError(400, 'Invalid availableOnly');
    if (req.query.availableOnly === 'true') query.isBooked = false;
  }
  res.json({ availability: await Availability.find(query).sort({ date: 1, startTime: 1 }).limit(200) });
});
export const updateAvailability = route(async (req: AuthRequest, res) => {
  const id = objectId(req.params.id);
  const input = schedule(req.body);
  const doctorId = req.user!.id;
  const availability = await mongoose.connection.transaction(async session => {
    await lockDoctor(doctorId, session);
    if (await Availability.exists({ _id: { $ne: id }, doctorId, date: input.date, startTime: { $lt: input.endTime }, endTime: { $gt: input.startTime } }).session(session)) {
      throw new HttpError(409, 'Overlapping availability');
    }
    const slot = await Availability.findOneAndUpdate({ _id: id, doctorId, isBooked: false }, { $set: input }, { session, new: true });
    if (!slot) throw new HttpError(409, 'Slot is booked, missing or not owned by you');
    return slot;
  });
  res.json({ availability });
});
export const deleteAvailability = route(async (req: AuthRequest, res) => {
  const id = objectId(req.params.id);
  const slot = await Availability.findOneAndDelete({ _id: id, doctorId: req.user!.id, isBooked: false });
  if (!slot) throw new HttpError(409, 'Slot is booked, missing or not owned by you');
  res.status(204).end();
});

import mongoose from 'mongoose';
import { config } from './index';
import { identityModels } from '../models/Identity';
import { User } from '../models/User';
import { Availability } from '../models/Availability';
import { Appointment } from '../models/Appointment';
export async function connectDB(): Promise<void> {
  await mongoose.connect(config.mongoUri);
  const hello = await mongoose.connection.db!.admin().command({ hello: 1 });
  if (!hello.setName) throw new Error('Booking requires a MongoDB replica set');
  // Index failure prevents listening; no requests run without the uniqueness invariant.
  await Promise.all([User.init(), Availability.init(), Appointment.init(), ...identityModels.map(model => model.init())]);
}
export const disconnectDB = (): Promise<void> => mongoose.disconnect();

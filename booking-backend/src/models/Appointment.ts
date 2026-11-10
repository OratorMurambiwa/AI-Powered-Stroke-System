import mongoose, { Document, Schema } from 'mongoose';

export interface IAppointment extends Document {
  appointmentUuid?: string;
  assessmentRequestId?: string;
  encounterId?: string;
  patientId: mongoose.Types.ObjectId;
  patientName: string;
  doctorId: mongoose.Types.ObjectId;
  doctorName: string;
  availabilityId: mongoose.Types.ObjectId;
  date: Date;
  startTime: string;
  endTime: string;
  status: 'confirmed' | 'cancelled' | 'completed';
  notes?: string;
  createdAt: Date;
  updatedAt: Date;
}

const appointmentSchema = new Schema<IAppointment>(
  {
    appointmentUuid: { type: String, unique: true, sparse: true },
    assessmentRequestId: String,
    encounterId: String,
    patientId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    patientName: {
      type: String,
      required: true,
    },
    doctorId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    doctorName: {
      type: String,
      required: true,
    },
    availabilityId: {
      type: Schema.Types.ObjectId,
      ref: 'Availability',
      required: true,
    },
    date: {
      type: Date,
      required: true,
    },
    startTime: {
      type: String,
      required: true,
    },
    endTime: {
      type: String,
      required: true,
    },
    status: {
      type: String,
      enum: ['confirmed', 'cancelled', 'completed'],
      default: 'confirmed',
    },
    notes: {
      type: String,
    },
  },
  {
    timestamps: true,
  }
);

// Database invariant: a slot has at most one confirmed appointment, including across processes.
appointmentSchema.index({ availabilityId: 1 }, {
  unique: true, partialFilterExpression: { status: 'confirmed' },
});
// Indexes for efficient querying
appointmentSchema.index({ patientId: 1, date: 1 });
appointmentSchema.index({ doctorId: 1, date: 1 });
appointmentSchema.index({ status: 1 });

export const Appointment = mongoose.model<IAppointment>(
  'Appointment',
  appointmentSchema
);
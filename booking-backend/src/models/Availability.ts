import mongoose, { Document, Schema } from 'mongoose';

export interface IAvailability extends Document {
  doctorId: mongoose.Types.ObjectId;
  doctorName: string;
  date: Date;
  startTime: string;
  endTime: string;
  isBooked: boolean;
  createdAt: Date;
  updatedAt: Date;
}

const availabilitySchema = new Schema<IAvailability>(
  {
    doctorId: {
      type: Schema.Types.ObjectId,
      ref: 'User',
      required: true,
    },
    doctorName: {
      type: String,
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
    isBooked: {
      type: Boolean,
      default: false,
    },
  },
  {
    timestamps: true,
  }
);

// Index for efficient querying
availabilitySchema.index({ doctorId: 1, date: 1 });
availabilitySchema.index({ date: 1, isBooked: 1 });

export const Availability = mongoose.model<IAvailability>(
  'Availability',
  availabilitySchema
);
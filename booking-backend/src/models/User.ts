import mongoose, { Document, Schema } from 'mongoose';
import bcrypt from 'bcryptjs';

export interface IUser extends Document {
  email: string;
  password: string;
  name: string;
  role: 'patient' | 'doctor' | 'physician' | 'technician' | 'admin';
  state: 'active' | 'invited' | 'revoked';
  authVersion: number;
  authWriteVersion: number;
  recoveryRequestedAt?: Date;
  createdAt: Date;
  scheduleVersion: number;
  comparePassword(candidatePassword: string): Promise<boolean>;
}

const userSchema = new Schema<IUser>(
  {
    email: {
      type: String,
      required: true,
      unique: true,
      lowercase: true,
      trim: true,
    },
    password: {
      type: String,
      required: true,
      minlength: 12,
      select: false,
    },
    name: {
      type: String,
      required: true,
      trim: true,
    },
    state: { type: String, enum: ['active', 'invited', 'revoked'], default: 'active' },
    authVersion: { type: Number, default: 0 },
    authWriteVersion: { type: Number, default: 0, select: false },
    recoveryRequestedAt: { type: Date, select: false },
    scheduleVersion: { type: Number, default: 0, select: false },
    role: {
      type: String,
      enum: ['patient', 'doctor', 'physician', 'technician', 'admin'],
      default: 'patient',
    },
  },
  {
    timestamps: true,
  }
);

// Hash password before saving
userSchema.pre('save', async function (next) {
  if (!this.isModified('password')) return next();

  try {
    const salt = await bcrypt.genSalt(10);
    this.password = await bcrypt.hash(this.password, salt);
    next();
  } catch (error: any) {
    next(error);
  }
});

// Method to compare passwords
userSchema.methods.comparePassword = async function (
  candidatePassword: string
): Promise<boolean> {
  return bcrypt.compare(candidatePassword, this.password);
};

export const User = mongoose.model<IUser>('User', userSchema);

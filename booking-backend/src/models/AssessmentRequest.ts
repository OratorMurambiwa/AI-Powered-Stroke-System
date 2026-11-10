import { Schema, model } from 'mongoose';
const schema = new Schema({
  _id: { type: String, required: true }, appointmentId: { type: String, required: true },
  actorId: { type: Schema.Types.ObjectId, required: true }, actorRoleVersion: { type: Number, required: true },
  sourceId: { type: String, required: true }, patientId: { type: String, required: true },
  patientMappingId: { type: String, required: true }, clinicianMappingId: { type: String, required: true },
  encounterId: { type: String, required: true }, intentHash: { type: String, required: true }, commandHash: { type: String, required: true },
  state: { type: String, enum: ['PENDING', 'CREATED', 'REJECTED'], required: true },
  blocking: { type: Boolean, required: true }, attempts: { type: Number, default: 0 },
  leaseId: String, leaseUntil: Date, lastErrorCode: { type: String, default: null },
}, { timestamps: true, versionKey: false });
schema.index({ appointmentId: 1 }, { unique: true, partialFilterExpression: { blocking: true } });
export const AssessmentRequest = model('AssessmentRequest', schema);

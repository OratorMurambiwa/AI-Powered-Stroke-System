import { Schema, model } from 'mongoose';
const session = new Schema({
  _id: { type: String, required: true }, userId: { type: Schema.Types.ObjectId, required: true, index: true },
  authVersion: { type: Number, required: true }, role: { type: String, required: true },
  issuedAt: { type: Date, required: true }, expiresAt: { type: Date, required: true },
  revokedAt: { type: Date, default: null },
}, { versionKey: false });
session.index({ expiresAt: 1 }, { expireAfterSeconds: 0 });
export const IdentitySession = model('IdentitySession', session);
const audit = new Schema({
  actor: { type: String, required: true, immutable: true }, subject: { type: String, immutable: true },
  action: { type: String, required: true, immutable: true }, reason: { type: String, immutable: true },
  fromRole: { type: String, immutable: true }, toRole: { type: String, immutable: true },
  at: { type: Date, required: true, immutable: true },
}, { versionKey: false, strict: 'throw' });
audit.index({ subject: 1, at: 1 });
export const IdentityAudit = model('IdentityAudit', audit);
export const IdentityControl = model('IdentityControl', new Schema({
  _id: String, version: { type: Number, default: 0 }, bootstrapComplete: { type: Boolean, default: false },
}, { versionKey: false }));
const challenge = new Schema({
  _id: { type: String, required: true }, userId: { type: Schema.Types.ObjectId, required: true, index: true },
  authVersion: { type: Number, required: true }, kind: { type: String, enum: ['activation', 'recovery'], required: true },
  expiresAt: { type: Date, required: true }, usedAt: { type: Date, default: null },
}, { versionKey: false });
challenge.index({ expiresAt: 1 }, { expireAfterSeconds: 0 });
export const IdentityChallenge = model('IdentityChallenge', challenge);
const delivery = new Schema({
  _id: { type: String, required: true }, userId: { type: Schema.Types.ObjectId, required: true },
  challengeHash: { type: String, required: true }, ciphertext: String, iv: String, tag: String,
  expiresAt: { type: Date, required: true }, consumedAt: { type: Date, default: null },
}, { versionKey: false });
delivery.index({ expiresAt: 1 }, { expireAfterSeconds: 0 });
export const IdentityDelivery = model('IdentityDelivery', delivery);
export const identityModels = [IdentitySession, IdentityAudit, IdentityControl, IdentityChallenge, IdentityDelivery];

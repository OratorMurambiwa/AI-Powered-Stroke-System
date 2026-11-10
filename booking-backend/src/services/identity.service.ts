import { randomBytes, randomUUID, createHash, createCipheriv, createDecipheriv } from 'node:crypto';
import mongoose, { ClientSession } from 'mongoose';
import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { config } from '../config';
import { IUser, User } from '../models/User';
import { IdentityAudit, IdentitySession, IdentityControl, IdentityChallenge, IdentityDelivery } from '../models/Identity';
import { canonicalRole, Role, staffRoles } from '../identity/roles';
import { HttpError, text } from '../utils/http';

export interface Principal { id: string; email: string; role: Role; sessionId: string; authVersion: number; expiresAt: number }
export function password(value: unknown): string {
  if (typeof value !== 'string' || value.length < 12 || Buffer.byteLength(value) > 72) throw new HttpError(400, 'Password must contain at least 12 characters and at most 72 UTF-8 bytes');
  return value;
}
export function email(value: unknown): string {
  const result = text(value, 254).toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(result)) throw new HttpError(400, 'Invalid email');
  return result;
}
export const tokenHash = (value: string): string => createHash('sha256').update(value).digest('hex');
export async function audit(session: ClientSession, action: string, actor: string, subject?: string,
    reason?: string, fromRole?: string, toRole?: string): Promise<void> {
  await IdentityAudit.create([{ action, actor, subject, reason, fromRole, toRole, at: new Date() }], { session });
}
function active(user: IUser): boolean { return (user.state ?? 'active') === 'active' && canonicalRole(user.role) !== undefined; }
export async function assertActor(principal: Principal, session: ClientSession, allowed?: readonly Role[]): Promise<IUser> {
  const current = await IdentitySession.findOne({ _id: principal.sessionId, userId: principal.id, revokedAt: null,
    expiresAt: { $gt: new Date() }, authVersion: principal.authVersion }).session(session);
  const user = await User.findById(principal.id).session(session);
  if (!current || !user || !active(user) || (user.authVersion ?? 0) !== principal.authVersion ||
      canonicalRole(user.role) !== current.role) throw new HttpError(401, 'Session is no longer active');
  if (allowed && !allowed.includes(canonicalRole(user.role)!)) throw new HttpError(403, 'Forbidden');
  // Serialize security-sensitive writes with password reset, logout-all and revocation.
  await User.updateOne({ _id: user._id }, { $inc: { authWriteVersion: 1 } }, { session });
  return user;
}
export async function issueSession(user: IUser, session: ClientSession) {
  if (!active(user)) throw new HttpError(401, 'Invalid credentials');
  const now = Math.floor(Date.now() / 1000);
  const sid = randomUUID();
  const expiresAt = now + config.jwt.expiresIn;
  await IdentitySession.create([{ _id: sid, userId: user._id, role: canonicalRole(user.role), authVersion: user.authVersion ?? 0,
    issuedAt: new Date(now * 1000), expiresAt: new Date(expiresAt * 1000) }], { session });
  return { token: jwt.sign({ ver: 1, sid, iat: now, exp: expiresAt }, config.jwt.secret,
      { subject: String(user._id), issuer: config.jwt.issuer, audience: config.jwt.audience, algorithm: 'HS256' }),
    expiresAt, user: { id: user._id, email: user.email, name: user.name, role: canonicalRole(user.role) } };
}
export async function authenticateToken(raw: string): Promise<Principal> {
  let claims: jwt.JwtPayload;
  try {
    const decoded = jwt.verify(raw, config.jwt.secret, { algorithms: ['HS256'], issuer: config.jwt.issuer, audience: config.jwt.audience });
    if (typeof decoded === 'string' || decoded.ver !== 1 || typeof decoded.sub !== 'string' || !/^[a-f0-9]{24}$/i.test(decoded.sub) ||
      typeof decoded.sid !== 'string' || !/^[a-f0-9-]{36}$/.test(decoded.sid) || decoded.aud !== config.jwt.audience ||
      !Number.isInteger(decoded.iat) || !Number.isInteger(decoded.exp) || decoded.exp! <= decoded.iat! ||
      decoded.exp! - decoded.iat! > 900 || decoded.iat! > Math.floor(Date.now() / 1000) + 5) throw new Error();
    claims = decoded;
  } catch { throw new HttpError(401, 'Invalid or expired token'); }
  // Do not accept a signature alone. Missing session / TTL cleanup delay / outages fail closed.
  const record = await IdentitySession.findOne({ _id: claims.sid, userId: claims.sub, revokedAt: null, expiresAt: { $gt: new Date() } });
  const user = await User.findById(claims.sub);
  const role = user && canonicalRole(user.role);
  if (!record || !user || !role || !active(user) || record.authVersion !== (user.authVersion ?? 0) ||
      record.role !== role || record.expiresAt.getTime() !== claims.exp! * 1000 || record.issuedAt.getTime() !== claims.iat! * 1000) {
    throw new HttpError(401, 'Session is no longer active');
  }
  return { id: user.id, email: user.email, role, sessionId: record.id, authVersion: record.authVersion, expiresAt: claims.exp! };
}
export async function invalidate(user: IUser, session: ClientSession): Promise<void> {
  await User.updateOne({ _id: user._id }, { $inc: { authVersion: 1 } }, { session });
  await IdentitySession.updateMany({ userId: user._id, revokedAt: null }, { $set: { revokedAt: new Date() } }, { session });
  await IdentityChallenge.updateMany({ userId: user._id, usedAt: null }, { $set: { usedAt: new Date() } }, { session });
  // Old delivery envelopes must never be usable after revocation/password change.
  await IdentityDelivery.updateMany({ userId: user._id, consumedAt: null }, { $set: { consumedAt: new Date() }, $unset: { ciphertext: '', iv: '', tag: '' } }, { session });
}
async function challenge(user: IUser, kind: 'activation' | 'recovery', session: ClientSession): Promise<string> {
  const token = randomBytes(32).toString('hex');
  const hash = tokenHash(token);
  const id = randomUUID();
  const expiresAt = new Date(Date.now() + config.recoveryTtlSeconds * 1000);
  await IdentityChallenge.updateMany({ userId: user._id, usedAt: null }, { $set: { usedAt: new Date() } }, { session });
  await IdentityDelivery.updateMany({ userId: user._id, consumedAt: null }, { $set: { consumedAt: new Date() }, $unset: { ciphertext: '', iv: '', tag: '' } }, { session });
  await IdentityChallenge.create([{ _id: hash, userId: user._id, authVersion: user.authVersion ?? 0, kind, expiresAt }], { session });
  const iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', config.deliveryKey, iv);
  cipher.setAAD(Buffer.from(`${id}:${hash}`));
  const ciphertext = Buffer.concat([cipher.update(JSON.stringify({ email: user.email, token, kind }), 'utf8'), cipher.final()]);
  await IdentityDelivery.create([{ _id: id, userId: user._id, challengeHash: hash,
    ciphertext: ciphertext.toString('hex'), iv: iv.toString('hex'), tag: cipher.getAuthTag().toString('hex'), expiresAt }], { session });
  return id;
}
async function governance(session: ClientSession): Promise<void> {
  await IdentityControl.findOneAndUpdate({ _id: 'staff-governance' }, { $inc: { version: 1 } }, { upsert: true, session, new: true });
}
export async function bootstrapAdmin(input: { email: string; name: string; reason: string }, operator: string) {
  if (process.env.ALLOW_IDENTITY_BOOTSTRAP !== 'true') throw new HttpError(403, 'Explicit local bootstrap opt-in required');
  const actor = 'operator:' + text(operator, 120);
  const reason = text(input.reason, 500);
  return mongoose.connection.transaction(async session => {
    await governance(session);
    const control = await IdentityControl.findById('staff-governance').session(session);
    if (control!.bootstrapComplete || await User.exists({ role: 'admin' }).session(session)) throw new HttpError(409, 'Identity bootstrap is already closed');
    const [user] = await User.create([{ email: email(input.email), name: text(input.name, 120), role: 'admin', state: 'invited', password: randomBytes(48).toString('hex') }], { session });
    const deliveryId = await challenge(user, 'activation', session);
    await IdentityControl.updateOne({ _id: 'staff-governance' }, { $set: { bootstrapComplete: true } }, { session });
    await audit(session, 'ADMIN_BOOTSTRAPPED', actor, user.id, reason, undefined, 'admin');
    return { id: user.id, deliveryId };
  });
}
export async function provisionStaff(principal: Principal, input: { email: unknown; name: unknown; role: unknown; reason: unknown; currentPassword: unknown }) {
  const role = canonicalRole(input.role);
  if (!role || !staffRoles.includes(role as typeof staffRoles[number])) throw new HttpError(400, 'Invalid staff role');
  const reason = text(input.reason, 500);
  return mongoose.connection.transaction(async session => {
    await governance(session);
    await reauthenticateAdmin(principal, input.currentPassword, session);
    // Duplicate email is a conflict, never promotion or implicit account linkage.
    const [user] = await User.create([{ email: email(input.email), name: text(input.name, 120), role, state: 'invited', password: randomBytes(48).toString('hex') }], { session });
    const deliveryId = await challenge(user, 'activation', session);
    await audit(session, 'STAFF_PROVISIONED', principal.id, user.id, reason, undefined, role);
    return { user: { id: user.id, role, state: user.state }, deliveryId };
  });
}
async function reauthenticateAdmin(principal: Principal, candidate: unknown, session: ClientSession): Promise<void> {
  await assertActor(principal, session, ['admin']);
  const actor = await User.findById(principal.id).select('+password').session(session);
  if (typeof candidate !== 'string' || Buffer.byteLength(candidate) > 72 || !await actor!.comparePassword(candidate)) throw new HttpError(401, 'Password verification required');
}
export async function changeStaff(principal: Principal, id: string, input: { reason: unknown; currentPassword: unknown; role?: unknown }, revoke: boolean) {
  const reason = text(input.reason, 500);
  const role = canonicalRole(input.role);
  if (!revoke && (!role || !staffRoles.includes(role as typeof staffRoles[number]))) throw new HttpError(400, 'Invalid staff role');
  if (id.toLowerCase() === principal.id.toLowerCase()) throw new HttpError(409, 'Self-revocation and self-role changes are not permitted');
  return mongoose.connection.transaction(async session => {
    await governance(session);
    await reauthenticateAdmin(principal, input.currentPassword, session);
    const target = await User.findById(id).session(session);
    if (!target || canonicalRole(target.role) === 'patient') throw new HttpError(404, 'Staff identity not found');
    if (target.state === 'revoked') throw new HttpError(409, 'Staff identity is already revoked');
    const from = canonicalRole(target.role);
    await User.updateOne({ _id: id }, { $set: revoke ? { state: 'revoked' } : { role } }, { session });
    await invalidate(target, session);
    await audit(session, revoke ? 'STAFF_REVOKED' : 'STAFF_ROLE_CHANGED', principal.id, id, reason, from, revoke ? undefined : role);
    return { id, role: revoke ? from : role, state: revoke ? 'revoked' : target.state };
  });
}
export async function requestRecovery(address: string): Promise<void> {
  await mongoose.connection.transaction(async session => {
    const user = await User.findOne({ email: address }).select('+recoveryRequestedAt').session(session);
    if (user && user.state !== 'revoked' && (!user.recoveryRequestedAt || user.recoveryRequestedAt.getTime() <= Date.now() - 60000)) {
      await User.updateOne({ _id: user._id }, { $set: { recoveryRequestedAt: new Date() }, $inc: { authWriteVersion: 1 } }, { session });
      await challenge(user, 'recovery', session);
    }
    await audit(session, 'RECOVERY_REQUESTED', 'anonymous');
  });
}
export async function resetPassword(raw: unknown, value: unknown): Promise<void> {
  if (typeof raw !== 'string' || !/^[a-f0-9]{64}$/.test(raw)) throw new HttpError(400, 'Invalid or expired recovery token');
  const hash = await bcrypt.hash(password(value), 10);
  await mongoose.connection.transaction(async session => {
    const record = await IdentityChallenge.findOneAndUpdate({ _id: tokenHash(raw), usedAt: null, expiresAt: { $gt: new Date() } }, { $set: { usedAt: new Date() } }, { session, new: true });
    if (!record) throw new HttpError(400, 'Invalid or expired recovery token');
    const user = await User.findById(record.userId).session(session);
    if (!user || user.state === 'revoked' || (user.authVersion ?? 0) !== record.authVersion) throw new HttpError(400, 'Invalid or expired recovery token');
    await User.updateOne({ _id: user._id }, { $set: { password: hash, state: 'active' }, $inc: { authWriteVersion: 1 } }, { session });
    await invalidate(user, session);
    await audit(session, record.kind === 'activation' ? 'STAFF_ACTIVATED' : 'PASSWORD_RECOVERED', user.id, user.id);
  });
}
// Local operator-only delivery adapter, never an HTTP endpoint. Explicit handoff
// consumes and clears the encrypted envelope. No sender, logs or external network.
export async function consumeDelivery(id: string, operator: string): Promise<{ email: string; token: string; kind: string }> {
  const actor = 'operator:' + text(operator, 120);
  return mongoose.connection.transaction(async session => {
    const record = await IdentityDelivery.findOne({ _id: id, consumedAt: null, expiresAt: { $gt: new Date() } }).session(session);
    if (!record?.ciphertext || !record.iv || !record.tag) throw new HttpError(404, 'Delivery unavailable');
    const token = await IdentityChallenge.findOne({ _id: record.challengeHash, usedAt: null, expiresAt: { $gt: new Date() } }).session(session);
    const user = await User.findById(record.userId).session(session);
    if (!token || !user || user.state === 'revoked' || token.authVersion !== (user.authVersion ?? 0)) throw new HttpError(404, 'Delivery unavailable');
    const decipher = createDecipheriv('aes-256-gcm', config.deliveryKey, Buffer.from(record.iv, 'hex'));
    decipher.setAAD(Buffer.from(`${record.id}:${record.challengeHash}`));
    decipher.setAuthTag(Buffer.from(record.tag, 'hex'));
    const payload = JSON.parse(Buffer.concat([decipher.update(Buffer.from(record.ciphertext, 'hex')), decipher.final()]).toString('utf8'));
    await IdentityDelivery.updateOne({ _id: id }, { $set: { consumedAt: new Date() }, $unset: { ciphertext: '', iv: '', tag: '' } }, { session });
    await audit(session, 'DELIVERY_HANDED_OFF', actor, String(record.userId));
    return payload;
  });
}

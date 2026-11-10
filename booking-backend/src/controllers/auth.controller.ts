import mongoose from 'mongoose';
import bcrypt from 'bcryptjs';
import { randomBytes } from 'node:crypto';
import { setTimeout as pause } from 'node:timers/promises';
import { User } from '../models/User';
import { IdentitySession } from '../models/Identity';
import { AuthRequest } from '../middleware/auth';
import { fields, text, HttpError, route } from '../utils/http';
import { audit, email, password, issueSession, assertActor, invalidate, requestRecovery, resetPassword } from '../services/identity.service';
// Random per-process dummy hash: unknown-user login performs the same bcrypt work.
const dummyHash = bcrypt.hashSync('not-a-user-' + randomBytes(32).toString('hex'), 10);
export const register = route(async (req, res) => {
  const body = fields(req.body, ['email', 'password', 'name', 'role']);
  if (body.role !== undefined && body.role !== 'patient') throw new HttpError(400, 'Public registration permits patients only');
  const address = email(body.email); const secret = password(body.password); const name = text(body.name, 120);
  const result = await mongoose.connection.transaction(async session => {
    const [user] = await User.create([{ email: address, password: secret, name, role: 'patient', state: 'active' }], { session });
    const result = await issueSession(user, session);
    await audit(session, 'PATIENT_REGISTERED', user.id, user.id);
    return result;
  });
  res.status(201).json(result);
});
export const login = route(async (req, res) => {
  const body = fields(req.body, ['email', 'password']); const address = email(body.email);
  if (typeof body.password !== 'string' || !body.password || Buffer.byteLength(body.password) > 72) throw new HttpError(400, 'Invalid password');
  const candidate = body.password;
  const result = await mongoose.connection.transaction(async session => {
    const user = await User.findOne({ email: address }).select('+password').session(session);
    const matches = await bcrypt.compare(candidate, user?.password || dummyHash);
    if (!user || !matches || (user.state ?? 'active') !== 'active') {
      await audit(session, 'LOGIN_FAILED', 'anonymous'); return undefined;
    }
    await User.updateOne({ _id: user._id }, { $inc: { authWriteVersion: 1 } }, { session });
    const result = await issueSession(user, session);
    await audit(session, 'LOGIN_SUCCEEDED', user.id, user.id);
    return result;
  });
  if (!result) throw new HttpError(401, 'Invalid credentials');
  res.json(result);
});
export const logout = route(async (req: AuthRequest, res) => {
  await mongoose.connection.transaction(async session => {
    await assertActor(req.user!, session);
    await IdentitySession.updateOne({ _id: req.user!.sessionId }, { $set: { revokedAt: new Date() } }, { session });
    await audit(session, 'SESSION_REVOKED', req.user!.id, req.user!.id);
  });
  res.status(204).end();
});
export const logoutAll = route(async (req: AuthRequest, res) => {
  await mongoose.connection.transaction(async session => {
    const user = await assertActor(req.user!, session);
    await invalidate(user, session);
    await audit(session, 'ALL_SESSIONS_REVOKED', user.id, user.id);
  });
  res.status(204).end();
});
export const changePassword = route(async (req: AuthRequest, res) => {
  const body = fields(req.body, ['currentPassword', 'newPassword']);
  const hash = await bcrypt.hash(password(body.newPassword), 10);
  await mongoose.connection.transaction(async session => {
    await assertActor(req.user!, session);
    const user = await User.findById(req.user!.id).select('+password').session(session);
    if (typeof body.currentPassword !== 'string' || Buffer.byteLength(body.currentPassword) > 72 || !await user!.comparePassword(body.currentPassword)) throw new HttpError(401, 'Password verification required');
    await User.updateOne({ _id: user!._id }, { $set: { password: hash } }, { session });
    await invalidate(user!, session);
    await audit(session, 'PASSWORD_CHANGED', user!.id, user!.id);
  });
  res.status(204).end();
});
export const recoveryRequest = route(async (req, res) => {
  const start = Date.now(); const body = fields(req.body, ['email']); const address = email(body.email);
  try { await requestRecovery(address); }
  finally { await pause(Math.max(0, 250 - (Date.now() - start))); }
  res.status(202).json({ message: 'If recovery is available, instructions will be delivered through the registered channel.' });
});
export const recoveryReset = route(async (req, res) => {
  const body = fields(req.body, ['token', 'newPassword']);
  await resetPassword(body.token, body.newPassword);
  res.status(204).end();
});

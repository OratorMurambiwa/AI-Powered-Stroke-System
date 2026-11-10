import jwt from 'jsonwebtoken';
import { User, IUser } from '../models/User';
import { config } from '../config';
import { fields, text, HttpError, route } from '../utils/http';
function credentials(body: unknown, registering: boolean): Record<string, unknown> & { email: string; password: string } {
  const data = fields(body, registering ? ['email', 'password', 'name', 'role'] : ['email', 'password']);
  const email = text(data.email, 254).toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new HttpError(400, 'Invalid email');
  if (typeof data.password !== 'string' || data.password.length < (registering ? 12 : 1) ||
      Buffer.byteLength(data.password) > 72) throw new HttpError(400, 'Invalid password (signup: 12 characters minimum, 72 bytes maximum)');
  return { ...data, email, password: data.password };
}
function result(user: IUser) {
  return {
    token: jwt.sign({}, config.jwt.secret, { subject: String(user._id), algorithm: 'HS256', expiresIn: config.jwt.expiresIn }),
    user: { id: user._id, email: user.email, name: user.name, role: user.role },
  };
}
export const register = route(async (req, res) => {
  const data = credentials(req.body, true);
  if (data.role !== undefined && data.role !== 'patient') throw new HttpError(400, 'Public registration permits patients only');
  const user = await User.create({ email: data.email, password: data.password, name: text(data.name, 120), role: 'patient' });
  res.status(201).json(result(user));
});
export const login = route(async (req, res) => {
  const data = credentials(req.body, false);
  const user = await User.findOne({ email: data.email }).select('+password');
  if (!user || !await user.comparePassword(data.password)) throw new HttpError(401, 'Invalid credentials');
  res.json(result(user));
});

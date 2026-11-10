import { Request, Response, NextFunction, RequestHandler } from 'express';
import jwt from 'jsonwebtoken';
import { config } from '../config';
import { User } from '../models/User';
export interface AuthRequest extends Request {
  user?: { id: string; email: string; role: string };
}
export const authenticate = async (req: AuthRequest, res: Response, next: NextFunction): Promise<void> => {
  const header = req.headers.authorization;
  if (!header?.startsWith('Bearer ')) { res.status(401).json({ error: 'Authentication required' }); return; }
  let id: string;
  try {
    const token = jwt.verify(header.slice(7), config.jwt.secret, { algorithms: ['HS256'] });
    if (typeof token === 'string' || typeof token.sub !== 'string' || !/^[a-f0-9]{24}$/i.test(token.sub)) throw new Error();
    id = token.sub;
  } catch { res.status(401).json({ error: 'Invalid or expired token' }); return; }
  try {
    const user = await User.findById(id).select('email role');
    if (!user) { res.status(401).json({ error: 'Invalid user' }); return; }
    // Authorization uses the current persisted role, never client or stale token claims.
    req.user = { id: user.id, email: user.email, role: user.role };
    next();
  } catch (error) { next(error); }
};
export const authorize = (...roles: string[]): RequestHandler => (req: AuthRequest, res, next) => {
  if (!req.user) { res.status(401).json({ error: 'Authentication required' }); return; }
  if (!roles.includes(req.user.role)) { res.status(403).json({ error: 'Forbidden' }); return; }
  next();
};

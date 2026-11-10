import { Request, RequestHandler } from 'express';
import { Principal, authenticateToken } from '../services/identity.service';
import { Role } from '../identity/roles';
export interface AuthRequest extends Request { user?: Principal }
export const authenticate: RequestHandler = (req: AuthRequest, _res, next) => {
  const header = req.headers.authorization;
  if (!header?.startsWith('Bearer ') || header.length > 4096) { _res.status(401).json({ error: 'Authentication required' }); return; }
  authenticateToken(header.slice(7)).then(user => { req.user = user; next(); }).catch(next);
};
export const authorize = (...roles: Role[]): RequestHandler => (req: AuthRequest, res, next) => {
  if (!req.user) { res.status(401).json({ error: 'Authentication required' }); return; }
  if (!roles.includes(req.user.role)) { res.status(403).json({ error: 'Forbidden' }); return; }
  next();
};

import { Router } from 'express';
import { authenticate, authorize, AuthRequest } from '../middleware/auth';
import { fields, objectId, route } from '../utils/http';
import { provisionStaff, changeStaff } from '../services/identity.service';
import { User } from '../models/User';
import { IdentityAudit, IdentitySession } from '../models/Identity';
const router = Router();
router.use((_req, res, next) => { res.setHeader('Cache-Control', 'no-store'); next(); });
router.use(authenticate);
function principal(req: AuthRequest) {
  const user = req.user!;
  return { schemaVersion: 1, issuer: 'urn:stroke-platform:identity:v1', subject: user.id,
    role: user.role, sessionId: user.sessionId, expiresAt: user.expiresAt };
}
router.get('/me', (req: AuthRequest, res) => { res.json(principal(req)); });
// Future Python services use live validation, not the HMAC signing key or Streamlit state.
router.post('/introspect', (req: AuthRequest, res, next) => {
  try { fields(req.body ?? {}, []); res.json({ active: true, ...principal(req) }); } catch (e) { next(e); }
});
// Separate closed contract: do not add fields to milestone-2A introspection v1.
router.post('/clinical-introspect', (req: AuthRequest, res, next) => {
  try {
    fields(req.body ?? {}, []);
    res.json({ active: true, ...principal(req), roleVersion: req.user!.roleVersion });
  } catch (e) { next(e); }
});
router.get('/sessions', route(async (req: AuthRequest, res) => {
  res.json({ schemaVersion: 1, sessions: await IdentitySession.find({ userId: req.user!.id, revokedAt: null,
    expiresAt: { $gt: new Date() } }).select('_id issuedAt expiresAt').limit(100) });
}));
router.get('/staff', authorize('admin'), route(async (_req, res) => {
  const users = await User.find({ role: { $in: ['doctor', 'physician', 'technician', 'admin'] } }).select('_id name email role state').sort({ _id: 1 }).limit(100);
  res.json({ schemaVersion: 1, limit: 100, staff: users.map(u => ({ id: u.id, name: u.name, email: u.email, role: u.role === 'physician' ? 'doctor' : u.role, state: u.state ?? 'active' })) });
}));
router.get('/staff/:id/audit', authorize('admin'), route(async (req, res) => {
  const id = objectId(req.params.id);
  res.json({ schemaVersion: 1, events: await IdentityAudit.find({ subject: id }).sort({ at: -1 }).limit(100) });
}));
router.post('/staff', authorize('admin'), route(async (req: AuthRequest, res) => {
  const body = fields(req.body, ['email', 'name', 'role', 'reason', 'currentPassword']);
  res.status(201).json({ schemaVersion: 1, ...await provisionStaff(req.user!, body as Parameters<typeof provisionStaff>[1]) });
}));
router.patch('/staff/:id/role', authorize('admin'), route(async (req: AuthRequest, res) => {
  const body = fields(req.body, ['role', 'reason', 'currentPassword']);
  res.json({ schemaVersion: 1, user: await changeStaff(req.user!, objectId(req.params.id), body as Parameters<typeof changeStaff>[2], false) });
}));
router.post('/staff/:id/revoke', authorize('admin'), route(async (req: AuthRequest, res) => {
  const body = fields(req.body, ['reason', 'currentPassword']);
  res.json({ schemaVersion: 1, user: await changeStaff(req.user!, objectId(req.params.id), body as Parameters<typeof changeStaff>[2], true) });
}));
export default router;

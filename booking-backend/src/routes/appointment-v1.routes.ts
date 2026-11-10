import { Router } from 'express';
import { authenticate, AuthRequest } from '../middleware/auth';
import { bookAppointment, cancelAppointmentRecord } from '../controllers/appointment.controller';
import { appointmentDto, ownedAppointment, reserve, deliver, result, proof } from '../services/assessment.service';
import { bookingLimiter } from '../middleware/rateLimiter';
import { fields, HttpError, route } from '../utils/http';
const router = Router();
router.use((req, res, next) => {
  res.setHeader('Cache-Control', 'no-store');
  if (!req.headers.authorization?.startsWith('Bearer ') || req.headers.authorization.length > 4096) { next(new HttpError(401, 'authentication_required')); return; }
  authenticate(req, res, next);
});
router.post('/', bookingLimiter, route(async (req: AuthRequest, res) => {
  if (req.user!.role !== 'patient') throw new HttpError(403, 'patient_required');
  const body = fields(req.body, ['schemaVersion', 'availabilityId', 'notes']);
  if (body.schemaVersion !== 1) throw new HttpError(400, 'unsupported_contract_version');
  req.body = { availabilityId: body.availabilityId, ...(body.notes === undefined ? {} : { notes: body.notes }) };
  const record = await bookAppointment(req);
  res.location(`/api/v1/appointments/${record.appointmentUuid}`).status(201).json(appointmentDto(record));
}));
router.get('/:id', route(async (req: AuthRequest, res) => { res.json(appointmentDto(await ownedAppointment(req.user!, req.params.id))); }));
router.patch('/:id/cancel', route(async (req: AuthRequest, res) => {
  const body = fields(req.body, ['schemaVersion']);
  if (body.schemaVersion !== 1) throw new HttpError(400, 'unsupported_contract_version');
  const owned = await ownedAppointment(req.user!, req.params.id);
  if (owned.assessmentRequestId) throw new HttpError(409, 'assessment_cancellation_requires_review');
  req.params.id = owned.id;
  res.json(appointmentDto(await cancelAppointmentRecord(req)));
}));
router.post('/:id/assessment-requests', route(async (req: AuthRequest, res) => {
  const record = await reserve(req.user!, req.params.id, req.body);
  let delivered;
  try { delivered = await deliver(req.user!, record, req.headers.authorization!); }
  catch { throw new HttpError(503, 'assessment_state_unavailable_retry_same_request'); }
  if (delivered.state === 'PENDING') res.setHeader('Retry-After', '4');
  res.status(delivered.state === 'PENDING' ? 202 : delivered.state === 'REJECTED' ? 422 : 200).json(result(delivered));
}));
router.post('/:id/assessment-proof', route(async (req: AuthRequest, res) => {
  const body = fields(req.body, ['schemaVersion', 'requestId']);
  if (body.schemaVersion !== 1) throw new HttpError(400, 'unsupported_contract_version');
  res.json(await proof(req.user!, req.params.id, body.requestId as string));
}));
export default router;

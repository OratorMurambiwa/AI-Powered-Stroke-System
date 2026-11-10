import { Router } from 'express';
import {
  createAppointment,
  getAppointments,
  getAppointment,
  cancelAppointment,
} from '../controllers/appointment.controller';
import { authenticate, authorize } from '../middleware/auth';
import { bookingLimiter } from '../middleware/rateLimiter';

const router = Router();

// All routes require authentication
router.post('/', authenticate, authorize('patient'), bookingLimiter, createAppointment);
router.get('/', authenticate, authorize('patient', 'doctor'), getAppointments);
router.get('/:id', authenticate, authorize('patient', 'doctor'), getAppointment);
router.patch('/:id/cancel', authenticate, authorize('patient', 'doctor'), cancelAppointment);

export default router;
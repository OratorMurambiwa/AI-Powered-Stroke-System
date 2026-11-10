import { Router } from 'express';
import {
  createAppointment,
  getAppointments,
  cancelAppointment,
} from '../controllers/appointment.controller';
import { authenticate, authorize } from '../middleware/auth';
import { bookingLimiter } from '../middleware/rateLimiter';

const router = Router();

// All routes require authentication
router.post('/', authenticate, authorize('patient'), bookingLimiter, createAppointment);
router.get('/', authenticate, getAppointments);
router.patch('/:id/cancel', authenticate, authorize('patient', 'doctor'), cancelAppointment);

export default router;
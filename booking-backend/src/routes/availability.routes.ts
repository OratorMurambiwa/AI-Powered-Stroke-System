import { Router } from 'express';
import {
  createAvailability,
  getAvailability,
  updateAvailability,
  deleteAvailability,
} from '../controllers/availability.controller';
import { authenticate, authorize } from '../middleware/auth';

const router = Router();

// Public route - anyone can view availability
router.get('/', getAvailability);

// Protected routes - doctors only
router.post('/', authenticate, authorize('doctor'), createAvailability);
router.put('/:id', authenticate, authorize('doctor'), updateAvailability);
router.delete('/:id', authenticate, authorize('doctor'), deleteAvailability);

export default router;
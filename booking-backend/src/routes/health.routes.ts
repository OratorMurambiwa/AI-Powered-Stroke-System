import { Router } from 'express';
import mongoose from 'mongoose';
const router = Router();
router.get('/', (_req, res) => {
  const ready = mongoose.connection.readyState === 1;
  res.status(ready ? 200 : 503).json({ status: ready ? 'ready' : 'unavailable' });
});
export default router;

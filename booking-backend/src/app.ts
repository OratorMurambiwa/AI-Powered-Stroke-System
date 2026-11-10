import express, { Application, Request, Response } from 'express';
import cors from 'cors';
import helmet from 'helmet';
import { apiLimiter } from './middleware/rateLimiter';
import identityRoutes from './routes/identity.routes';
import authRoutes from './routes/auth.routes';
import availabilityRoutes from './routes/availability.routes';
import appointmentV1Routes from './routes/appointment-v1.routes';
import appointmentRoutes from './routes/appointment.routes';
import healthRoutes from './routes/health.routes';
import { errorHandler } from './utils/http';

const app: Application = express();

// Security middleware
app.use(helmet());
app.use(cors({ origin: false }));

// Body parsing middleware
app.use(express.json({ limit: '16kb' }));
app.use(express.urlencoded({ extended: true }));

// Global rate limiting
app.use(apiLimiter);

// Private portal responses must not be stored by browsers or proxies.
app.use('/api', (_req, res, next) => { res.setHeader('Cache-Control', 'no-store'); next(); });

// Routes
app.use('/api/auth', authRoutes); // Milestone-1 URL compatibility, same authority.
app.use('/api/v1/identity/auth', authRoutes);
app.use('/api/v1/identity', identityRoutes);
app.use('/api/availability', availabilityRoutes);
app.use('/api/appointments', appointmentRoutes);
app.use('/api/v1/appointments', appointmentV1Routes);
app.use('/api/health', healthRoutes);

// Root route
app.get('/', (req: Request, res: Response) => {
  res.json({
    message: 'Hospital Appointment Booking API',
    version: '1.0.0',
    endpoints: {
      auth: '/api/auth',
      availability: '/api/availability',
      appointments: '/api/appointments',
      health: '/api/health',
    },
  });
});

// 404 handler
app.use((req: Request, res: Response) => {
  res.status(404).json({ error: 'Route not found' });
});

app.use(errorHandler);
export default app;

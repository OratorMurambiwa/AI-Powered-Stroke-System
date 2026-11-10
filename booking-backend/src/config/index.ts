import dotenv from 'dotenv';
dotenv.config();
const secret = process.env.JWT_SECRET;
if (!secret || Buffer.byteLength(secret) < 32) {
  throw new Error('JWT_SECRET must contain at least 32 bytes; no default secret is provided');
}
export const config = {
  port: Number(process.env.PORT || 3000),
  nodeEnv: process.env.NODE_ENV || 'development',
  mongoUri: process.env.MONGODB_URI || 'mongodb://127.0.0.1:27017/hospital-booking?replicaSet=rs0',
  redis: { host: process.env.REDIS_HOST || 'localhost', port: Number(process.env.REDIS_PORT || 6379) },
  jwt: { secret, expiresIn: 86400 },
  cache: { ttl: 300 },
  rateLimit: { windowMs: 900000, maxRequests: Number(process.env.RATE_LIMIT_MAX_REQUESTS || 100) },
};

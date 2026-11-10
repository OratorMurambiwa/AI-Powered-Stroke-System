import dotenv from 'dotenv';
dotenv.config();
const secret = process.env.JWT_SECRET;
if (!secret || Buffer.byteLength(secret) < 32) throw new Error('JWT_SECRET must contain at least 32 bytes; no default secret is provided');
const deliveryKey = process.env.IDENTITY_DELIVERY_KEY;
if (!deliveryKey || !/^[a-f0-9]{64}$/i.test(deliveryKey)) throw new Error('IDENTITY_DELIVERY_KEY must be a separately generated 32-byte hex key');
if (deliveryKey === secret) throw new Error('Identity signing and delivery keys must differ');
const ttl = Number(process.env.JWT_TTL_SECONDS || 900);
if (!Number.isInteger(ttl) || ttl < 60 || ttl > 900) throw new Error('JWT_TTL_SECONDS must be an integer from 60 to 900');
export const config = {
  port: Number(process.env.PORT || 3000),
  nodeEnv: process.env.NODE_ENV || 'development',
  mongoUri: process.env.MONGODB_URI || 'mongodb://127.0.0.1:27017/hospital-booking?replicaSet=rs0',
  jwt: { secret, expiresIn: ttl, issuer: 'urn:stroke-platform:identity:v1', audience: 'urn:stroke-platform:booking:v1' },
  deliveryKey: Buffer.from(deliveryKey, 'hex'),
  recoveryTtlSeconds: 900,
  rateLimit: { windowMs: 900000, maxRequests: Number(process.env.RATE_LIMIT_MAX_REQUESTS || 100) },
};

import { Request, Response, NextFunction, RequestHandler } from 'express';
import mongoose from 'mongoose';
export class HttpError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export const route = (handler: (req: Request, res: Response) => Promise<void>): RequestHandler =>
  (req, res, next) => { Promise.resolve(handler(req, res)).catch(next); };
export function objectId(value: unknown): string {
  if (typeof value !== 'string' || !/^[a-fA-F0-9]{24}$/.test(value)) throw new HttpError(400, 'Invalid ID');
  return value.toLowerCase();
}
export function fields(value: unknown, allowed: string[]): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).some(key => !allowed.includes(key))) throw new HttpError(400, 'Invalid fields');
  return value as Record<string, unknown>;
}
export function text(value: unknown, max: number): string {
  if (typeof value !== 'string' || !value.trim() || value.length > max) throw new HttpError(400, 'Invalid text');
  return value.trim();
}
export function day(value: unknown): Date {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new HttpError(400, 'Expected YYYY-MM-DD');
  const date = new Date(value + 'T00:00:00.000Z');
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value) throw new HttpError(400, 'Invalid date');
  return date;
}
export function times(start: unknown, end: unknown): { startTime: string; endTime: string } {
  const valid = (v: unknown): v is string => typeof v === 'string' && /^([01]\d|2[0-3]):[0-5]\d$/.test(v);
  if (!valid(start) || !valid(end) || start >= end) throw new HttpError(400, 'Invalid time interval');
  return { startTime: start, endTime: end };
}
export function errorHandler(error: unknown, req: Request, res: Response, _next: NextFunction): void {
  const versioned = req.originalUrl.startsWith('/api/v1/appointments');
  const reply = (status: number, message: string) => res.status(status).json({ ...(versioned ? { schemaVersion: 1 } : {}), error: message });
  if (error instanceof HttpError) { reply(error.status, error.message); return; }
  if (error instanceof mongoose.mongo.MongoServerError && error.code === 11000) {
    reply(409, versioned ? 'idempotency_or_reservation_conflict' : 'Resource already exists or slot is booked'); return;
  }
  if (error instanceof mongoose.Error.ValidationError || error instanceof SyntaxError) {
    reply(400, versioned ? 'invalid_request' : 'Invalid request'); return;
  }
  reply(500, versioned ? 'internal_error' : 'Internal server error');
}

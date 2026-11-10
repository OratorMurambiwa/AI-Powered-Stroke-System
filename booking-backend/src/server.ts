import app from './app';
import { config } from './config';
import { connectDB, disconnectDB } from './config/database';
import logger from './utils/logger';
async function start(): Promise<void> {
  await connectDB();
  const server = app.listen(config.port, '127.0.0.1', () => logger.info('Booking API started on loopback'));
  for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => {
    server.close(() => { void disconnectDB().then(() => process.exit(0)); });
    setTimeout(() => process.exit(1), 10000).unref();
  });
}
void start().catch(async () => {
  logger.error('Booking API startup failed');
  await disconnectDB();
  process.exitCode = 1;
});

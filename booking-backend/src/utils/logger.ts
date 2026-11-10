import winston from 'winston';
// Log fixed event descriptions only. Never attach requests, DB errors or patient data.
export default winston.createLogger({
  level: process.env.NODE_ENV === 'test' ? 'error' : 'info',
  format: winston.format.json(),
  transports: [new winston.transports.Console()],
});

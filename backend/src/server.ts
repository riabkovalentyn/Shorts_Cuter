import express from 'express';
import cors from 'cors';
import morgan from 'morgan';
import path from 'node:path';
import { router as apiRouter } from './web/api';

export async function createServer() {
  const app = express();

  app.use(cors({ origin: '*'}));
  app.use(express.json({ limit: '10mb' }));
  app.use(morgan('dev'));

  // Static serve generated media if needed
  const storageDir = process.env.STORAGE_DIR || path.resolve(process.cwd(), 'storage');
  app.use('/storage', express.static(storageDir));

  app.use('/api', apiRouter);

  // health
  app.get('/health', (_req: express.Request, res: express.Response) => res.json({ ok: true }));

  // Error handler
  app.use((err: any, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    console.error('Unhandled error:', err);
    res.status(500).json({ error: 'Internal Server Error' });
  });

  return app;
}

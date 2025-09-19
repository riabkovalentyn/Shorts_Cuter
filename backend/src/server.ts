import express from 'express';
import cors from 'cors';
import morgan from 'morgan';
import path from 'node:path';
import fs from 'node:fs';
import { router as apiRouter } from './web/api';

export async function createServer() {
  const app = express();

  app.use(cors({ origin: '*'}));
  app.use(express.json({ limit: '10mb' }));
  app.use(morgan('dev'));

  // Root - basic info instead of 404
  app.get('/', (_req, res) => {
    res.json({ ok: true, name: 'Shorts Cuter API', health: '/health', api: '/api' });
  });

  // Static serve generated media if needed
  const storageDir = process.env.STORAGE_DIR || path.resolve(__dirname, '..', '..', 'storage');
  console.log(`[backend] storage dir: ${storageDir}`);
  // Guard: return 404 for zero-byte files to avoid RangeNotSatisfiable
  app.use('/storage', (req, res, next) => {
    const relative = req.path.replace(/^[/\\]+/, '');
    const requested = path.normalize(path.join(storageDir, relative));
    if (!requested.startsWith(storageDir)) return res.status(400).end();
    fs.stat(requested, (err, stat) => {
      if (!err && stat.isFile() && stat.size === 0) {
        return res.status(404).json({ error: 'File is empty' });
      }
      next();
    });
  });
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

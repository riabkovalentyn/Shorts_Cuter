import { Router, Request, Response } from 'express';
import { ingestProject } from '../../workflows/ingestWorkflow';

const router = Router();

// POST /api/projects
router.post('/', async (req: Request, res: Response) => {
  const { sourceUrl, clipLengthSec } = req.body || {};
  if (!sourceUrl) return res.status(400).json({ error: 'sourceUrl is required' });
  const job = await ingestProject({ sourceUrl, clipLengthSec: Number(clipLengthSec) || 30 });
  res.status(202).json({ jobId: job._id, status: job.status });
});

export default router;

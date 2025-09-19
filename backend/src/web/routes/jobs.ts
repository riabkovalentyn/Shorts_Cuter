import { Router, Request, Response } from 'express';
import Job from '../../models/Job';

const router = Router();

// GET /api/jobs/:id — статус задачи
router.get('/:id', async (req: Request, res: Response) => {
  const job = await Job.findById(req.params.id).lean();
  if (!job) return res.status(404).json({ error: 'Not found' });
  res.json(job);
});

export default router;

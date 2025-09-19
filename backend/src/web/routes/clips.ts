import { Router, Request, Response } from 'express';
import Clip from '../../models/Clip';
import { uploadClipToYouTube } from '../../services/youtubeService';

const router = Router();

// GET /api/clips?jobId=...
router.get('/', async (req: Request, res: Response) => {
  const { jobId } = req.query as { jobId?: string };
  const q = jobId ? { jobId } : {};
  const clips = await Clip.find(q).lean();
  res.json(clips);
});

// POST /api/clips/:clipId/upload
router.post('/:clipId/upload', async (req: Request, res: Response) => {
  const clip = await Clip.findById(req.params.clipId);
  if (!clip) return res.status(404).json({ error: 'Not found' });
  const result = await uploadClipToYouTube(clip);
  res.json(result);
});

export default router;

import { Router, Request, Response } from 'express';
import Clip from '../../models/Clip';
import { uploadClipToYouTube } from '../../services/youtubeService';

const router = Router();

// GET /api/clips?jobId=...
router.get('/', async (req: Request, res: Response) => {
  const { jobId } = req.query as { jobId?: string };
  const q = jobId ? { jobId } : {};
  const clips = await Clip.find(q).lean();
  const toPublic = (p?: string) => {
    if (!p) return p;
    const idx = p.toLowerCase().lastIndexOf('storage');
    const rel = idx >= 0 ? p.slice(idx + 'storage'.length + 1) : p;
    return `/storage/${rel.replace(/\\\\/g, '/')}`;
  };
  const data = clips.map((c: any) => ({
    ...c,
    fileUrl: toPublic(c.filePath),
    thumbUrl: toPublic(c.thumbPath),
  }));
  res.json(data);
});

// POST /api/clips/:clipId/upload
router.post('/:clipId/upload', async (req: Request, res: Response) => {
  const clip = await Clip.findById(req.params.clipId);
  if (!clip) return res.status(404).json({ error: 'Not found' });
  const result = await uploadClipToYouTube(clip);
  res.json(result);
});

export default router;

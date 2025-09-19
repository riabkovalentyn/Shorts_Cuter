import { Router, Request, Response } from 'express';
import { getAuthUrl, handleOAuthCallback } from '../../services/youtubeService';

const router = Router();

// GET /api/auth/youtube/url
router.get('/url', async (_req: Request, res: Response) => {
  const url = await getAuthUrl();
  res.json({ url });
});

// GET /api/auth/youtube/callback
router.get('/callback', async (req: Request, res: Response) => {
  const code = req.query.code as string;
  if (!code) return res.status(400).json({ error: 'code required' });
  const result = await handleOAuthCallback(code);
  // In production, redirect to frontend success page.
  res.json(result);
});

export default router;

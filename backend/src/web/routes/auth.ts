import { Router, Request, Response } from 'express';
import { getAuthUrl, handleOAuthCallback } from '../../services/youtubeService';
import Token from '../../models/Token';

const router = Router();

// GET /api/auth/youtube/url
router.get('/url', async (_req: Request, res: Response) => {
  try {
    const url = await getAuthUrl();
    res.json({ url });
  } catch (err: any) {
    res.status(400).json({ error: err?.message || 'Failed to create auth URL' });
  }
});

// GET /api/auth/youtube/callback
router.get('/callback', async (req: Request, res: Response) => {
  const code = req.query.code as string;
  if (!code) return res.status(400).json({ error: 'code required' });
  const result = await handleOAuthCallback(code);
  // In production, redirect to frontend success page.
  res.json(result);
});

// GET /api/auth/youtube/status
router.get('/status', async (_req: Request, res: Response) => {
  const configured = Boolean(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET);
  const token = await Token.findOne({ provider: 'youtube' }).lean();
  const connected = Boolean(token?.refreshToken);
  res.json({ configured, connected });
});

export default router;
